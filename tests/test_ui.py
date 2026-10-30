"""The web UI's server side, tested over raw HTTP: the built app served at `/ui`, the
who-am-I route, cookie sign-in with CSRF protection, the Knowledge Graph list summaries,
and `stetiq ui` (local mode, no tokens).

The React app itself is tested in the browser by Playwright (`frontend/e2e`).
"""

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

import stetiq
from stetiq.auth import TokenRegistry
from stetiq.cli import app
from stetiq.graph_source import InMemoryGraphSource
from stetiq.server import create_app
from stetiq.tracking import wire

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


# --- Sign-in with an API Token -------------------------------------------------------------


def issue(database_url, grants, user="ada"):
    """A fresh API Token's secret value."""
    return TokenRegistry(database_url).issue(user, grants)[1]


def set_cookie_headers(response) -> dict[str, str]:
    """Each `Set-Cookie` header of `response`, by cookie name."""
    headers = response.headers.get_list("set-cookie")
    return {h.split("=", 1)[0]: h for h in headers}


def test_signing_in_keeps_the_token_in_an_httponly_strict_cookie(http, database_url):
    token = issue(database_url, {"support": "read"})

    r = http.post("/auth/sign-in", json={"token": token})

    assert r.status_code == 200
    assert r.json() == {"mode": "server", "user": "ada", "grants": {"support": "read"}}
    cookie = set_cookie_headers(r)["stetiq_token"].lower()
    assert f"stetiq_token={token}".lower() in cookie
    assert "httponly" in cookie
    assert "samesite=strict" in cookie
    assert "path=/;" in cookie or cookie.endswith("path=/")


@pytest.mark.parametrize("token", ["stq_nope_nope", ""])
def test_signing_in_with_an_invalid_token_is_refused_with_a_message(http, token):
    r = http.post("/auth/sign-in", json={"token": token})

    assert r.status_code == 401
    assert r.json()["error"]["message"]
    assert "set-cookie" not in r.headers


def test_signing_in_with_a_revoked_token_is_refused(http, database_url):
    registry = TokenRegistry(database_url)
    issued, token = registry.issue("ada", {"support": "read"})
    registry.revoke(issued.id)

    assert http.post("/auth/sign-in", json={"token": token}).status_code == 401


@pytest.fixture
def two_graphs(database_url, support_ontology):
    """`support` and `billing`, each with one finished Construction Run."""
    sdk = stetiq.Client(database_url, graph_source=InMemoryGraphSource())
    runs = {}
    for kg in ("support", "billing"):
        sdk.create_knowledge_graph(kg, ontology=support_ontology)
        sdk.bind_graph_source(kg, stetiq.GraphSourceScope(database="neo4j"))
        with sdk.start_run(kg) as run:
            pass
        runs[kg] = run.id
    return runs


def sign_in(http, database_url, grants, user="ada"):
    r = http.post("/auth/sign-in", json={"token": issue(database_url, grants, user)})
    assert r.status_code == 200, r.text


def test_the_api_accepts_the_sign_in_cookie_with_the_tokens_read_rules(
    http, database_url, two_graphs
):
    sign_in(http, database_url, {"support": "read"})

    assert http.get("/api/v1/whoami").json()["user"] == "ada"
    assert [kg["name"] for kg in http.get("/api/v1/knowledge-graphs").json()] == ["support"]
    assert http.get("/api/v1/knowledge-graphs/support").status_code == 200
    assert http.get(f"/api/v1/runs/{two_graphs['support']}").status_code == 200
    assert http.get("/api/v1/knowledge-graphs/billing").status_code == 403


def test_a_run_outside_the_cookies_grants_is_as_not_found_as_an_unknown_one(
    http, database_url, two_graphs
):
    sign_in(http, database_url, {"support": "read"})

    hidden = http.get(f"/api/v1/runs/{two_graphs['billing']}")
    unknown = http.get("/api/v1/runs/no-such-run")

    assert hidden.status_code == unknown.status_code == 404
    assert hidden.json()["error"]["type"] == unknown.json()["error"]["type"] == "NotFoundError"


def test_signing_in_also_sets_a_csrf_cookie_that_page_scripts_can_read(http, database_url):
    sign_in(http, database_url, {"support": "read"})

    assert http.cookies.get("stetiq_csrf")
    r = http.post("/auth/sign-in", json={"token": issue(database_url, {"support": "read"})})
    csrf = set_cookie_headers(r)["stetiq_csrf"].lower()
    assert "httponly" not in csrf
    assert "samesite=strict" in csrf


def move_staging(http, headers=None):
    return http.put(
        "/api/v1/knowledge-graphs/support/aliases/staging",
        json={"version": 1, "actor": "ignored"},
        headers=headers,
    )


def test_a_cookie_authenticated_write_needs_the_matching_csrf_header(
    http, database_url, two_graphs
):
    sign_in(http, database_url, {"support": "edit"})
    csrf = http.cookies["stetiq_csrf"]

    missing = move_staging(http)
    wrong = move_staging(http, {"X-CSRF-Token": "forged"})
    matching = move_staging(http, {"X-CSRF-Token": csrf})

    assert missing.status_code == wrong.status_code == 403
    assert "CSRF" in missing.json()["error"]["message"]
    assert matching.status_code == 200


def test_a_cookie_still_needs_edit_to_write(http, database_url, two_graphs):
    sign_in(http, database_url, {"support": "read"})

    r = http.put(
        "/api/v1/knowledge-graphs/support/aliases/staging",
        json={"version": 1},
        headers={"X-CSRF-Token": http.cookies["stetiq_csrf"]},
    )

    assert r.status_code == 403
    assert r.json()["error"]["type"] == "PermissionDeniedError"


def test_bearer_writes_need_no_csrf_header(http, database_url, two_graphs):
    r = move_staging(http, bearer(database_url, {"support": "edit"}))

    assert r.status_code == 200


def test_the_ui_promotes_without_sending_an_actor_and_the_audit_records_the_tokens_user(
    http, database_url, two_graphs
):
    sign_in(http, database_url, {"support": "edit"}, user="grace")

    r = http.put(
        "/api/v1/knowledge-graphs/support/aliases/staging",
        json={"version": 1},
        headers={"X-CSRF-Token": http.cookies["stetiq_csrf"]},
    )

    assert r.status_code == 200, r.text
    promotions = http.get("/api/v1/knowledge-graphs/support/promotions").json()
    assert [(p["alias"], p["to_version"], p["actor"]) for p in promotions][-1] == (
        "staging",
        1,
        "grace",
    )


def test_signing_out_clears_the_cookies(http, database_url):
    sign_in(http, database_url, {"support": "read"})

    r = http.post("/auth/sign-out")

    assert r.status_code == 204
    assert set(set_cookie_headers(r)) == {"stetiq_token", "stetiq_csrf"}
    assert not http.cookies.get("stetiq_token")
    assert http.get("/api/v1/whoami").status_code == 401


def test_a_revoked_token_in_the_cookie_is_refused(http, database_url):
    registry = TokenRegistry(database_url)
    issued, token = registry.issue("ada", {"support": "read"})
    assert http.post("/auth/sign-in", json={"token": token}).status_code == 200

    registry.revoke(issued.id)

    assert http.get("/api/v1/whoami").status_code == 401


def test_stetiq_ui_has_nothing_to_sign_in_to(database_url, frontend_dir):
    app = create_app(database_url, frontend_dir=frontend_dir, local_actor="grace")
    with TestClient(app) as http:
        r = http.post("/auth/sign-in", json={"token": "stq_any_thing"})

    assert r.status_code == 400
    assert "set-cookie" not in r.headers


# --- Knowledge Graph list summaries -------------------------------------------------------


def test_the_knowledge_graph_list_shows_only_readable_ones_with_their_summary(
    http, database_url, support_ontology
):
    sdk = stetiq.Client(database_url)
    sdk.create_knowledge_graph("support", ontology=support_ontology)
    sdk.create_knowledge_graph("billing", ontology=support_ontology)
    sdk.register_ontology("support", "node_types:\n  - label: Customer\n")

    r = http.get("/api/v1/knowledge-graphs", headers=bearer(database_url, {"support": "read"}))

    assert r.status_code == 200
    [support] = r.json()
    assert support["name"] == "support"
    assert (support["contract_version"], support["latest_version"]) == (1, 2)
    assert support["last_run_status"] is None
    assert (
        support["last_modified_at"] == sdk.list_knowledge_graphs()[1].last_modified_at.isoformat()
    )


def test_a_knowledge_graph_payload_without_summary_fields_still_parses():
    kg = wire.knowledge_graph_from_json({"name": "support", "created_at": "2026-01-02T03:04:05"})

    assert kg.name == "support"
    assert kg.contract_version is None
    assert kg.latest_version is None
    assert kg.last_run_status is None
    assert kg.last_modified_at is None
    assert kg.description is None


# --- Knowledge Graph description ------------------------------------------------------------


def describe_support(http, headers=None):
    return http.put(
        "/api/v1/knowledge-graphs/support/description",
        json={"description": "Answers support questions."},
        headers=headers,
    )


def test_a_read_only_token_cannot_set_the_description(http, database_url, two_graphs):
    r = describe_support(http, bearer(database_url, {"support": "read"}))

    assert r.status_code == 403
    assert r.json()["error"]["type"] == "PermissionDeniedError"
    readable = http.get(
        "/api/v1/knowledge-graphs/support", headers=bearer(database_url, {"*": "read"})
    )
    assert readable.json()["description"] is None


def test_an_editor_sets_the_description_through_the_sign_in_cookie(http, database_url, two_graphs):
    sign_in(http, database_url, {"support": "edit"})

    refused = describe_support(http)
    r = describe_support(http, {"X-CSRF-Token": http.cookies["stetiq_csrf"]})

    assert refused.status_code == 403
    assert r.status_code == 200
    assert http.get("/api/v1/knowledge-graphs/support").json()["description"] == (
        "Answers support questions."
    )


# --- Ontology Diff ------------------------------------------------------------------------


@pytest.fixture
def two_versions(database_url):
    """`support` v1 (Customer, Ticket) and v2 (Customer, Agent): Ticket removed, Agent added."""
    sdk = stetiq.Client(database_url)
    sdk.create_knowledge_graph(
        "support", ontology="node_types:\n  - label: Customer\n  - label: Ticket\n"
    )
    sdk.register_ontology("support", "node_types:\n  - label: Customer\n  - label: Agent\n")
    return "support"


def test_the_diff_route_returns_the_classified_changes_between_two_versions(
    http, database_url, two_versions
):
    r = http.get(
        "/api/v1/knowledge-graphs/support/ontology-diff",
        params={"base": 1, "target": 2},
        headers=bearer(database_url, {"support": "read"}),
    )

    assert r.status_code == 200, r.text
    assert r.json() == {
        "classification": "breaking",
        "changes": [
            {
                "concept": "Agent",
                "concept_kind": "node_type",
                "kind": "added",
                "classification": "additive",
                "detail": "node type Agent added",
            },
            {
                "concept": "Ticket",
                "concept_kind": "node_type",
                "kind": "removed",
                "classification": "breaking",
                "detail": "node type Ticket removed",
            },
        ],
    }


def diff(http, kg, base, target, headers):
    return http.get(
        f"/api/v1/knowledge-graphs/{kg}/ontology-diff",
        params={"base": base, "target": target},
        headers=headers,
    )


def test_diffing_a_version_against_itself_shows_no_changes(http, database_url, two_versions):
    r = diff(http, "support", 2, 2, bearer(database_url, {"support": "read"}))

    assert r.status_code == 200
    assert r.json() == {"classification": None, "changes": []}


def test_an_unknown_version_or_one_outside_the_tokens_grants_is_a_uniform_404(
    http, database_url, two_versions
):
    reader = bearer(database_url, {"billing": "read"})
    sdk = stetiq.Client(database_url)
    sdk.create_knowledge_graph("billing", ontology="node_types:\n  - label: Invoice\n")

    unknown = diff(http, "billing", 1, 9, reader)
    hidden = diff(http, "support", 1, 2, reader)
    hidden_unknown = diff(http, "nope", 1, 2, reader)

    assert unknown.status_code == hidden.status_code == hidden_unknown.status_code == 404
    assert {r.json()["error"]["type"] for r in (unknown, hidden, hidden_unknown)} == {
        "NotFoundError"
    }
    # An existing Knowledge Graph outside the grants reads exactly like a missing one.
    assert hidden.json()["error"]["message"] == "Knowledge Graph 'support' does not exist"
    assert hidden_unknown.json()["error"]["message"] == "Knowledge Graph 'nope' does not exist"


# --- Competency Question editing ------------------------------------------------------------
# The UI saves an edited Use Case through the existing Use Case Version registration route.


def register_use_case(http, headers=None):
    return http.post(
        "/api/v1/knowledge-graphs/support/use-case-versions",
        json={"use_case": {"competency_questions": [{"id": "names", "question": "Who?"}]}},
        headers=headers,
    )


def test_a_read_only_cookie_cannot_register_a_use_case_version(http, database_url, two_graphs):
    sign_in(http, database_url, {"support": "read"})

    r = register_use_case(http, {"X-CSRF-Token": http.cookies["stetiq_csrf"]})

    assert r.status_code == 403
    assert r.json()["error"]["type"] == "PermissionDeniedError"
    assert http.get("/api/v1/knowledge-graphs/support/use-case-versions").json() == []


def test_an_editor_registers_a_use_case_version_through_the_sign_in_cookie(
    http, database_url, two_graphs
):
    sign_in(http, database_url, {"support": "edit"})
    csrf = {"X-CSRF-Token": http.cookies["stetiq_csrf"]}

    first = register_use_case(http, csrf)
    unchanged = register_use_case(http, csrf)

    assert first.status_code == unchanged.status_code == 200
    assert first.json()["number"] == unchanged.json()["number"] == 1


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
