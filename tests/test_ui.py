"""The web UI's server side, tested over raw HTTP: the built app served at `/ui`, the
who-am-I route, and `stetiq ui` (local mode, no tokens).

The React app itself is tested in the browser by Playwright (`frontend/e2e`).
"""

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

import stetiq
from stetiq.auth import TokenRegistry
from stetiq.cli import app
from stetiq.server import create_app

SHELL = "<!doctype html><title>stetiq</title><div id=root></div>"


@pytest.fixture
def database_url(tmp_path):
    return f"sqlite:///{tmp_path / 'server.db'}"


@pytest.fixture
def frontend_dir(tmp_path):
    """A stand-in for the built frontend: an app shell and one hashed asset."""
    built = tmp_path / "frontend"
    (built / "assets").mkdir(parents=True)
    (built / "index.html").write_text(SHELL)
    (built / "assets" / "index-abc123.js").write_text("console.log('stetiq')")
    return built


@pytest.fixture
def http(database_url, frontend_dir):
    with TestClient(create_app(database_url, frontend_dir=frontend_dir)) as c:
        yield c


def bearer(database_url, grants, user="ada"):
    return {"Authorization": f"Bearer {TokenRegistry(database_url).issue(user, grants)[1]}"}


# --- The built app at /ui ----------------------------------------------------------------


@pytest.mark.parametrize("path", ["/ui", "/ui/", "/ui/settings", "/ui/kg/support/versions/3"])
def test_ui_paths_return_the_app_shell_so_deep_links_work(http, path):
    r = http.get(path)

    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/html")
    assert r.text == SHELL


def test_built_assets_are_served_as_files(http):
    r = http.get("/ui/assets/index-abc123.js")

    assert r.status_code == 200
    assert r.text == "console.log('stetiq')"
    assert "immutable" in r.headers["cache-control"]


def test_ui_paths_never_reach_files_outside_the_build(http, tmp_path):
    (tmp_path / "secret.txt").write_text("nope")

    r = http.get("/ui/..%2Fsecret.txt")

    assert "nope" not in r.text


def test_the_server_root_sends_you_to_the_ui(http):
    r = http.get("/", follow_redirects=False)

    assert r.status_code in (302, 307) and r.headers["location"] == "/ui/"


def test_the_api_is_not_shadowed_by_the_ui(http):
    assert http.get("/api/v1/knowledge-graphs").status_code == 401


# --- Who-am-I ------------------------------------------------------------------------------


def test_who_am_i_reports_the_tokens_user_and_grants_in_server_mode(http, database_url):
    headers = bearer(database_url, {"support": "read", "billing": "edit"})

    r = http.get("/api/v1/whoami", headers=headers)

    assert r.status_code == 200
    assert r.json() == {
        "mode": "server",
        "user": "ada",
        "grants": {"support": "read", "billing": "edit"},
    }


def test_who_am_i_needs_a_token_in_server_mode(http):
    assert http.get("/api/v1/whoami").status_code == 401


def test_who_am_i_reports_local_mode_where_every_knowledge_graph_is_editable(
    database_url, frontend_dir
):
    app = create_app(database_url, frontend_dir=frontend_dir, local_actor="grace")
    with TestClient(app) as http:
        r = http.get("/api/v1/whoami")

    assert r.json() == {"mode": "local", "user": "grace", "grants": {"*": "edit"}}


# --- stetiq ui ----------------------------------------------------------------------------


@pytest.fixture
def served(monkeypatch):
    """Captures what `stetiq ui` would hand to uvicorn instead of serving it."""
    calls = []
    monkeypatch.setattr("uvicorn.run", lambda app, **kw: calls.append({"app": app, **kw}))
    return calls


def test_stetiq_ui_serves_the_local_tracking_database_without_tokens(
    served, tmp_path, monkeypatch, support_ontology
):
    uri = f"sqlite:///{tmp_path / 'stetiq.db'}"
    monkeypatch.setenv("STETIQ_TRACKING_URI", uri)
    monkeypatch.setenv("STETIQ_ACTOR", "grace")
    sdk = stetiq.Client(uri)
    sdk.create_knowledge_graph("support", ontology=support_ontology)
    sdk.register_ontology("support", "node_types:\n  - label: Customer\n")

    result = CliRunner().invoke(app, ["ui", "--port", "5123"])

    assert result.exit_code == 0, result.output
    [call] = served
    assert (call["host"], call["port"]) == ("127.0.0.1", 5123)
    with TestClient(call["app"]) as http:
        assert http.get("/api/v1/whoami").json()["mode"] == "local"
        assert [kg["name"] for kg in http.get("/api/v1/knowledge-graphs").json()] == ["support"]
        moved = http.put(
            "/api/v1/knowledge-graphs/support/aliases/staging", json={"version": 2, "actor": "x"}
        )
        assert moved.status_code == 200
    assert sdk.list_promotions("support")[-1].actor == "grace"


def test_stetiq_ui_refuses_a_non_loopback_host_without_no_auth(served, tmp_path):
    uri = f"sqlite:///{tmp_path / 'stetiq.db'}"

    refused = CliRunner().invoke(app, ["ui", "--tracking-uri", uri, "--host", "0.0.0.0"])
    allowed = CliRunner().invoke(
        app, ["ui", "--tracking-uri", uri, "--host", "0.0.0.0", "--no-auth"]
    )

    assert refused.exit_code == 2
    assert "--no-auth" in refused.output
    assert allowed.exit_code == 0, allowed.output
    assert [c["host"] for c in served] == ["0.0.0.0"]


@pytest.mark.parametrize("host", ["localhost", "::1", "127.0.0.2"])
def test_stetiq_ui_accepts_any_loopback_host(served, tmp_path, host):
    uri = f"sqlite:///{tmp_path / 'stetiq.db'}"

    result = CliRunner().invoke(app, ["ui", "--tracking-uri", uri, "--host", host])

    assert result.exit_code == 0, result.output


def test_stetiq_ui_needs_a_local_tracking_uri(served):
    result = CliRunner().invoke(app, ["ui", "--tracking-uri", "http://stetiq.example:5000"])

    assert result.exit_code == 1
    assert "/ui" in result.output
    assert served == []
