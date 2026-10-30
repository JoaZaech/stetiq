"""The read-only web UI, tested over HTTP against the real server app.

Data is seeded through the SDK in local mode on the same database the server reads.
The UI authenticates with an API Token entered once and kept in an HttpOnly cookie.
"""

import re
from datetime import date

import pytest
from fastapi.testclient import TestClient

import stetiq
from stetiq.auth import TokenRegistry
from stetiq.graph_source import GraphSourceScope, InMemoryGraphSource
from stetiq.server import create_app

KG = "support"

V1 = """
node_types:
  - label: Customer
    properties:
      - {name: name, type: STRING, required: true}
  - label: Ticket
    properties:
      - {name: opened_at, type: DATE}
relationship_types: [OPENED]
patterns:
  - [Customer, OPENED, Ticket]
"""

V2 = """
node_types:
  - label: Customer
    properties:
      - {name: name, type: STRING, required: true}
  - label: Agent
relationship_types: [OPENED]
patterns: []
"""


@pytest.fixture
def database_url(tmp_path):
    return f"sqlite:///{tmp_path / 'server.db'}"


@pytest.fixture
def graph_source():
    return InMemoryGraphSource()


@pytest.fixture
def sdk(database_url, graph_source):
    return stetiq.Client(database_url, actor="ada", graph_source=graph_source)


@pytest.fixture
def http(database_url, sdk):
    with TestClient(create_app(database_url=database_url)) as c:
        yield c


def issue(database_url, grants):
    return TokenRegistry(database_url).issue("ada", grants)[1]


def log_in(http, value):
    return http.post("/ui/login", data={"token": value}, follow_redirects=False)


@pytest.fixture
def reader(http, database_url):
    """An HTTP client logged in with a token that reads every Knowledge Graph."""
    log_in(http, issue(database_url, {"*": "read"}))
    return http


# --- Authentication --------------------------------------------------------------------


def test_without_a_token_the_ui_sends_you_to_the_login_page(http):
    r = http.get("/ui", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/ui/login"
    assert "API token" in http.get("/ui/login").text


def test_logging_in_keeps_the_token_in_an_http_only_cookie(http, database_url):
    r = log_in(http, issue(database_url, {"*": "read"}))
    assert r.status_code == 303 and r.headers["location"] == "/ui"
    cookie = r.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=strict" in cookie
    assert http.get("/ui", follow_redirects=False).status_code == 200


def test_an_invalid_token_is_rejected_at_login(http):
    r = log_in(http, "stq_00000000_nope")
    assert r.status_code == 401
    assert "Invalid or revoked" in r.text


def test_a_revoked_token_in_the_cookie_sends_you_back_to_login(http, database_url):
    registry = TokenRegistry(database_url)
    t, value = registry.issue("ada", {"*": "read"})
    log_in(http, value)
    registry.revoke(t.id)
    r = http.get("/ui", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/ui/login"


def test_logging_out_forgets_the_token(reader):
    reader.post("/ui/logout")
    assert reader.get("/ui", follow_redirects=False).status_code == 303


# --- Knowledge Graphs, Ontology Versions and Aliases ------------------------------------


def test_the_index_lists_the_knowledge_graphs_the_token_can_read(http, sdk, database_url):
    sdk.create_knowledge_graph("support", ontology=V1)
    sdk.create_knowledge_graph("billing", ontology=V1)
    sdk.create_knowledge_graph("secret", ontology=V1)
    log_in(http, issue(database_url, {"support": "read", "billing": "edit"}))

    page = http.get("/ui").text

    assert 'href="/ui/kg/support"' in page and 'href="/ui/kg/billing"' in page
    assert "secret" not in page


def test_with_nothing_readable_the_index_says_so(reader):
    assert "No Knowledge Graphs" in reader.get("/ui").text


def test_a_knowledge_graph_page_lists_its_ontology_versions_newest_first_with_aliases(reader, sdk):
    sdk.create_knowledge_graph(KG, ontology=V1)
    sdk.register_ontology(KG, V2)
    sdk.set_alias(KG, "staging", 2)

    page = reader.get(f"/ui/kg/{KG}").text

    assert "Ontology Versions" in page
    assert page.index('id="v2"') < page.index('id="v1"')
    v2, v1 = page.split('id="v2"')[1].split('id="v1"')
    assert "staging" in v2 and "production" not in v2
    assert "production" in v1
    assert "Contract Alias" in page


def test_a_knowledge_graph_the_token_cannot_read_is_forbidden(http, sdk, database_url):
    sdk.create_knowledge_graph("secret", ontology=V1)
    log_in(http, issue(database_url, {"support": "read"}))
    assert http.get("/ui/kg/secret").status_code == 403


def test_an_unknown_knowledge_graph_is_not_found(reader):
    assert reader.get("/ui/kg/nope").status_code == 404


def test_page_content_is_html_escaped_and_urls_quoted(reader, sdk):
    sdk.create_knowledge_graph("a<b> c", ontology=V1)
    page = reader.get("/ui").text
    assert "a&lt;b&gt; c" in page and "a<b>" not in page
    assert 'href="/ui/kg/a%3Cb%3E%20c"' in page


# --- Construction Runs ---------------------------------------------------------------


@pytest.fixture
def runs(sdk, graph_source):
    """Two finished Construction Runs on `support` with different metrics."""
    sdk.create_knowledge_graph(KG, ontology=V1)
    sdk.bind_graph_source(KG, GraphSourceScope(database="neo4j"))
    ada = graph_source.add_node(["Customer"], {"name": "Ada"})
    ticket = graph_source.add_node(["Ticket"], {"opened_at": date(2026, 1, 1)})
    graph_source.add_relationship(ada, "OPENED", ticket)
    ids = []
    for f1, model in ((0.71, "small"), (0.83, "large")):
        with sdk.start_run(KG) as run:
            run.log_param("model", model)
            run.log_metric("f1", f1)
            if model == "large":
                run.log_metric("recall", 0.9)
        ids.append(run.id)
    return ids


def test_the_runs_table_has_a_column_per_metric(reader, runs):
    page = reader.get(f"/ui/kg/{KG}/runs").text

    header = page.split("<thead>")[1].split("</thead>")[0]
    assert "f1" in header and "recall" in header
    assert "0.71" in page and "0.83" in page and "0.9" in page
    assert all(run_id[:8] in page for run_id in runs)


def test_without_runs_the_runs_page_says_so(reader, sdk):
    sdk.create_knowledge_graph(KG, ontology=V1)
    assert "No Construction Runs" in reader.get(f"/ui/kg/{KG}/runs").text


def test_comparing_runs_puts_their_params_and_metrics_side_by_side(reader, runs):
    a, b = runs
    page = reader.get(f"/ui/kg/{KG}/runs/compare", params=[("run", a), ("run", b)]).text

    model_row = page.split(">model<")[1].split("</tr>")[0]
    assert model_row.index("small") < model_row.index("large")
    recall_row = page.split(">recall<")[1].split("</tr>")[0]
    assert "0.9" in recall_row and "—" in recall_row  # the first run did not log recall


def test_comparing_runs_of_another_knowledge_graph_is_not_found(reader, runs, sdk):
    sdk.create_knowledge_graph("billing", ontology=V1)
    r = reader.get("/ui/kg/billing/runs/compare", params=[("run", runs[0])])
    assert r.status_code == 404
    assert "not a Construction Run of" in r.text


# --- Ontology Diff -----------------------------------------------------------------------


def classified_changes(page):
    """(classification, concept) per change row of the diff table."""
    body = page.split("<tbody>")[1].split("</tbody>")[0]
    out = []
    for row in body.split("<tr")[1:]:
        cells = [c.split(">", 1)[1].split("</td>")[0] for c in row.split("<td")[1:]]
        out.append((cells[0], cells[2]))
    return out


def test_the_diff_view_classifies_each_change_between_two_versions(reader, sdk):
    sdk.create_knowledge_graph(KG, ontology=V1)
    sdk.register_ontology(KG, V2)

    page = reader.get(f"/ui/kg/{KG}/diff", params={"base": 1, "target": 2}).text

    changes = classified_changes(page)
    assert ("additive", "Agent") in changes
    assert ("breaking", "Ticket") in changes
    assert "Overall: breaking" in re.sub(r"<[^>]+>", "", page)


def test_the_diff_view_defaults_to_contract_against_latest(reader, sdk):
    sdk.create_knowledge_graph(KG, ontology=V1)
    sdk.register_ontology(KG, V2)

    page = reader.get(f"/ui/kg/{KG}/diff").text

    assert '<option value="1" selected>' in page.split('name="base"')[1].split("</select>")[0]
    assert '<option value="2" selected>' in page.split('name="target"')[1].split("</select>")[0]
    assert ("additive", "Agent") in classified_changes(page)


def test_diffing_a_version_against_itself_shows_no_changes(reader, sdk):
    sdk.create_knowledge_graph(KG, ontology=V1)
    page = reader.get(f"/ui/kg/{KG}/diff", params={"base": 1, "target": 1}).text
    assert "No changes" in page


def test_diffing_an_unknown_version_is_not_found(reader, sdk):
    sdk.create_knowledge_graph(KG, ontology=V1)
    assert reader.get(f"/ui/kg/{KG}/diff", params={"base": 1, "target": 9}).status_code == 404


# --- Drift -------------------------------------------------------------------------------


def test_drift_events_are_listed_with_their_contract_and_findings(reader, sdk, graph_source):
    sdk.create_knowledge_graph(KG, ontology=V1)
    sdk.bind_graph_source(KG, GraphSourceScope(database="neo4j"))
    ada = graph_source.add_node(["Customer"], {"name": "Ada"})
    graph_source.add_relationship(ada, "OPENED", graph_source.add_node(["Ticket"], {}))
    graph_source.add_node(["Agent"], {"name": "Grace"})
    sdk.observe(KG)

    page = reader.get(f"/ui/kg/{KG}/drift").text

    assert "production" in page and "v1" in page
    assert "undeclared" in page and "Agent" in page


def test_without_drift_the_drift_page_says_so(reader, sdk):
    sdk.create_knowledge_graph(KG, ontology=V1)
    assert "No Drift" in reader.get(f"/ui/kg/{KG}/drift").text
