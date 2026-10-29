"""Server mode end to end: `stetiq server` running for real, selected by tracking URI.

The behaviour itself is covered by the whole SDK suite running in `remote` mode
(see conftest); these tests cover starting the server and URI-based mode selection.
"""

import os
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
            sys.executable, "-c", "from stetiq.cli import app; app()",
            "server", "--host", "127.0.0.1", "--port", str(port), "--database-url", database_url,
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


@pytest.fixture(
    params=["sqlite", pytest.param("postgres", marks=pytest.mark.postgres)]
)
def server_url(request, tmp_path):
    if request.param == "sqlite":
        database_url = f"sqlite:///{tmp_path / 'server.db'}"
    else:
        from conftest import _postgres_url

        database_url = _postgres_url()
    proc, url = _start_server(database_url)
    yield url
    proc.terminate()
    proc.wait(timeout=10)


def test_sdk_selects_remote_mode_from_an_http_tracking_uri(server_url, support_ontology, monkeypatch):
    stetiq.Client(server_url).create_knowledge_graph("customer-support-kg", ontology=support_ontology)
    monkeypatch.setenv("STETIQ_TRACKING_URI", server_url)

    versions = stetiq.Client().list_ontology_versions("customer-support-kg")

    assert [v.number for v in versions] == [1]
    with pytest.raises(stetiq.NotFoundError):
        stetiq.Client(server_url).get_knowledge_graph("no-such-kg")


def test_cli_selects_remote_mode_from_an_http_tracking_uri(server_url, tmp_path, support_ontology, monkeypatch):
    ontology = tmp_path / "ontology.yaml"
    ontology.write_text(support_ontology)
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()

    created = runner.invoke(
        cli_app, ["kg", "create", "customer-support-kg", "--ontology", str(ontology), "--tracking-uri", server_url]
    )
    monkeypatch.setenv("STETIQ_TRACKING_URI", server_url)
    fetched = runner.invoke(cli_app, ["ontology", "get", "customer-support-kg", "1"])
    duplicate = runner.invoke(cli_app, ["kg", "create", "customer-support-kg", "--ontology", str(ontology)])

    assert created.exit_code == 0, created.output
    assert yaml.safe_load(fetched.output)["patterns"] == [["Customer", "OPENED", "Ticket"]]
    # Nothing was written locally: the data lives on the server.
    assert not (tmp_path / ".stetiq").exists()
    assert duplicate.exit_code == 1
    assert "already exists" in duplicate.output


def test_server_revalidates_ontologies_it_receives(tmp_path):
    with TestClient(create_app(f"sqlite:///{tmp_path / 'server.db'}")) as http:
        response = http.post(
            "/api/v1/knowledge-graphs",
            json={
                "name": "customer-support-kg",
                "declared_ontology": {"node_types": [{"label": "Customer"}], "patterns": [["Customer", "OPENED", "Ticket"]]},
            },
        )
        missing = http.get("/api/v1/knowledge-graphs/customer-support-kg")

    assert response.status_code == 422
    assert response.json()["error"]["type"] == "OntologyValidationError"
    assert "patterns[0]" in response.json()["error"]["message"]
    assert missing.status_code == 404
