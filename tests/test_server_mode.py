"""Server mode end to end: `stetiq server` running for real, selected by tracking URI.

The behaviour itself is covered by the whole SDK suite running in `remote` mode
(see conftest); these tests cover starting the server and URI-based mode selection.
"""

import socket
import subprocess
import sys
import time

import httpx
import pytest
import yaml
from fastapi.testclient import TestClient
from typer.testing import CliRunner

import stetiq
from stetiq.auth import TokenRegistry
from stetiq.cli import app as cli_app
from stetiq.server import create_app


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _start_server(database_url: str):
    port = _free_port()
    proc = subprocess.Popen(
        [
            sys.executable,
            "-c",
            "from stetiq.cli import app; app()",
            "server",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--database-url",
            database_url,
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )
    url = f"http://127.0.0.1:{port}"
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            raise RuntimeError(f"server exited: {proc.stderr.read().decode()}")
        try:
            if httpx.get(url + "/health").status_code == 200:
                return proc, url
        except httpx.TransportError:
            time.sleep(0.1)
    proc.kill()
    raise RuntimeError("server did not start")


def _issue_token_with_cli(database_url: str, user: str, *grants: str) -> str:
    args = ["token", "create", user, "--database-url", database_url]
    for grant in grants:
        args += ["--grant", grant]
    result = CliRunner().invoke(cli_app, args)
    assert result.exit_code == 0, result.output
    return result.output.strip().splitlines()[-1]


@pytest.fixture(params=["sqlite", pytest.param("postgres", marks=pytest.mark.postgres)])
def server(request, tmp_path):
    """A running server, as (url, database_url)."""
    if request.param == "sqlite":
        database_url = f"sqlite:///{tmp_path / 'server.db'}"
    else:
        from conftest import _postgres_url

        database_url = _postgres_url()
    proc, url = _start_server(database_url)
    yield url, database_url
    proc.terminate()
    proc.wait(timeout=10)


@pytest.fixture
def server_url(server, monkeypatch):
    """A running server, with an admin token (edit on every KG) in $STETIQ_TOKEN."""
    url, database_url = server
    monkeypatch.setenv("STETIQ_TOKEN", _issue_token_with_cli(database_url, "admin", "*=edit"))
    return url


def test_the_server_rejects_requests_without_a_token(server, monkeypatch):
    monkeypatch.delenv("STETIQ_TOKEN", raising=False)

    with pytest.raises(stetiq.AuthenticationError):
        stetiq.Client(server[0]).get_knowledge_graph("customer-support-kg")


def test_an_admin_issues_tokens_against_the_database_and_clients_pass_them(
    server, support_ontology, monkeypatch
):
    url, database_url = server
    monkeypatch.delenv("STETIQ_TOKEN", raising=False)
    admin = stetiq.Client(url, token=_issue_token_with_cli(database_url, "admin", "*=edit"))
    admin.create_knowledge_graph("customer-support-kg", ontology=support_ontology)
    reader_token = _issue_token_with_cli(database_url, "ada", "customer-support-kg=read")

    reader = stetiq.Client(url, token=reader_token)

    assert reader.get_knowledge_graph("customer-support-kg").name == "customer-support-kg"
    with pytest.raises(stetiq.PermissionDeniedError):
        reader.set_alias("customer-support-kg", "production", 1)


def test_tokens_can_be_listed_and_revoked_with_the_cli(server, monkeypatch):
    url, database_url = server
    monkeypatch.delenv("STETIQ_TOKEN", raising=False)
    token = _issue_token_with_cli(database_url, "ada", "kg=read", "other=edit")
    token_id = token.split("_")[1]
    runner = CliRunner()

    listed = runner.invoke(cli_app, ["token", "list", "--database-url", database_url])
    revoked = runner.invoke(cli_app, ["token", "revoke", token_id, "--database-url", database_url])

    assert listed.exit_code == 0, listed.output
    assert token_id in listed.output and "ada" in listed.output
    assert "kg=read" in listed.output and "other=edit" in listed.output
    assert token not in listed.output  # the secret is shown once, at issue time
    assert revoked.exit_code == 0, revoked.output
    with pytest.raises(stetiq.AuthenticationError):
        stetiq.Client(url, token=token).get_knowledge_graph("kg")


def test_sdk_selects_remote_mode_from_an_http_tracking_uri(
    server_url, support_ontology, monkeypatch
):
    stetiq.Client(server_url).create_knowledge_graph(
        "customer-support-kg", ontology=support_ontology
    )
    monkeypatch.setenv("STETIQ_TRACKING_URI", server_url)

    versions = stetiq.Client().list_ontology_versions("customer-support-kg")

    assert [v.number for v in versions] == [1]
    with pytest.raises(stetiq.NotFoundError):
        stetiq.Client(server_url).get_knowledge_graph("no-such-kg")


def test_cli_selects_remote_mode_from_an_http_tracking_uri(
    server_url, tmp_path, support_ontology, monkeypatch
):
    ontology = tmp_path / "ontology.yaml"
    ontology.write_text(support_ontology)
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()

    created = runner.invoke(
        cli_app,
        [
            "kg",
            "create",
            "customer-support-kg",
            "--ontology",
            str(ontology),
            "--tracking-uri",
            server_url,
        ],
    )
    monkeypatch.setenv("STETIQ_TRACKING_URI", server_url)
    fetched = runner.invoke(cli_app, ["ontology", "get", "customer-support-kg", "1"])
    duplicate = runner.invoke(
        cli_app, ["kg", "create", "customer-support-kg", "--ontology", str(ontology)]
    )

    assert created.exit_code == 0, created.output
    assert yaml.safe_load(fetched.output)["patterns"] == [["Customer", "OPENED", "Ticket"]]
    # Nothing was written locally: the data lives on the server.
    assert not (tmp_path / ".stetiq").exists()
    assert duplicate.exit_code == 1
    assert "already exists" in duplicate.output


def test_server_revalidates_ontologies_it_receives(tmp_path):
    database_url = f"sqlite:///{tmp_path / 'server.db'}"
    _, token = TokenRegistry(database_url).issue("admin", {"*": "edit"})
    with TestClient(create_app(database_url), headers={"Authorization": f"Bearer {token}"}) as http:
        response = http.post(
            "/api/v1/knowledge-graphs",
            json={
                "name": "customer-support-kg",
                "declared_ontology": {
                    "node_types": [{"label": "Customer"}],
                    "patterns": [["Customer", "OPENED", "Ticket"]],
                },
            },
        )
        missing = http.get("/api/v1/knowledge-graphs/customer-support-kg")

    assert response.status_code == 422
    assert response.json()["error"]["type"] == "OntologyValidationError"
    assert "patterns[0]" in response.json()["error"]["message"]
    assert missing.status_code == 404
