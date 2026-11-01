"""What the stetiq server must not take on the client's word.

A token with edit permission can send any request body, not only what the SDK sends.
These tests talk HTTP to the server directly, the way such a client would.
"""

import pytest
from fastapi.testclient import TestClient

import stetiq
from stetiq.auth import TokenRegistry
from stetiq.graph_source import InMemoryGraphSource
from stetiq.server import create_app
from stetiq.tracking import RemoteTrackingService, wire

API = wire.API_PREFIX

WITHOUT_OPENED = """
node_types:
  - label: Customer
    properties:
      - {name: name, type: STRING, required: true}
  - label: Ticket
    description: A support request
    properties:
      - {name: opened_at, type: DATE}
"""


@pytest.fixture
def server(tmp_path):
    database_url = f"sqlite:///{tmp_path / 'server.db'}"
    with TestClient(create_app(database_url)) as http:
        yield database_url, http


def _headers(server, user, grants):
    _, value = TokenRegistry(server[0]).issue(user, grants)
    return {"Authorization": f"Bearer {value}"}


@pytest.fixture
def admin(server):
    _, http = server
    url = str(http.base_url)
    _, token = TokenRegistry(server[0]).issue("admin", {"*": "edit"})
    graph_source = InMemoryGraphSource()
    service = RemoteTrackingService(url, http=http, token=token)
    return stetiq.Client(url, service=service, graph_source=graph_source)


@pytest.fixture
def support(admin, support_ontology):
    """`support`, with a breaking v2 (removes OPENED) and a finished run on v1."""
    admin.create_knowledge_graph("support", ontology=support_ontology)
    admin.register_ontology("support", WITHOUT_OPENED)
    admin.bind_graph_source("support", stetiq.GraphSourceScope(database="neo4j"))
    with admin.start_run("support", ontology_version=1):
        pass
    return "support"


def _run_id(admin, kg):
    return admin.list_runs(kg)[-1].id


# --- Gate results are computed by the server -------------------------------------------

NO_BREAKING = {
    "name": "no-breaking-changes",
    "check": "ontology_diff",
    "max_classification": "deprecating",
}


def test_a_gate_result_records_the_servers_outcome_not_the_clients(server, admin, support):
    _, http = server
    editor = _headers(server, "mallory", {"support": "edit"})

    response = http.post(
        f"{API}/knowledge-graphs/support/gate-results",
        headers=editor,
        json={
            "gates": [NO_BREAKING],
            "version": 2,
            # A forged outcome is not something the server takes.
            "outcomes": [{"gate": NO_BREAKING, "passed": True, "reasons": []}],
        },
    )

    assert response.status_code == 201, response.text
    [result] = admin.list_gate_results(support)
    assert not result.passed
    assert any("OPENED" in r for r in result.outcomes[0].reasons)


def test_the_promotion_audit_shows_a_bypassed_gate_as_failed(server, admin, support):
    _, http = server
    editor = _headers(server, "mallory", {"support": "edit"})
    http.post(
        f"{API}/knowledge-graphs/support/gate-results",
        headers=editor,
        json={"gates": [NO_BREAKING], "version": 2},
    )

    admin.set_alias(support, "production", 2)

    assert admin.list_promotions(support)[-1].gate_result == "failed"


def test_a_gate_result_needs_gate_definitions(server, support):
    _, http = server
    editor = _headers(server, "mallory", {"support": "edit"})

    response = http.post(
        f"{API}/knowledge-graphs/support/gate-results",
        headers=editor,
        json={"gates": [{"check": "nonsense"}], "version": 2},
    )

    assert response.status_code == 422


# --- Built-in Evaluator names are reserved ---------------------------------------------


@pytest.mark.parametrize(
    "evaluator",
    [
        "hierarchy",
        "structural_answerability",
        "competency_question_coverage",
        "definitions",
        "conformance",
        "observed_schema",
    ],
)
def test_results_under_built_in_evaluator_names_are_rejected(server, admin, support, evaluator):
    _, http = server
    editor = _headers(server, "mallory", {"support": "edit"})

    for path in (
        f"{API}/knowledge-graphs/support/ontology-versions/1/evaluations",
        f"{API}/knowledge-graphs/support/runs/{_run_id(admin, support)}/evaluations",
    ):
        response = http.post(
            path, headers=editor, json={"evaluator": evaluator, "metrics": {"x": 1}}
        )
        assert response.status_code == 422, (path, response.text)


def test_executed_competency_questions_are_accepted_only_for_runs(server, admin, support):
    _, http = server
    editor = _headers(server, "mallory", {"support": "edit"})
    body = {"evaluator": "competency_question_execution", "metrics": {"executed": 1}}

    on_version = http.post(
        f"{API}/knowledge-graphs/support/ontology-versions/1/evaluations", headers=editor, json=body
    )
    on_run = http.post(
        f"{API}/knowledge-graphs/support/runs/{_run_id(admin, support)}/evaluations",
        headers=editor,
        json=body,
    )

    assert on_version.status_code == 422
    assert on_run.status_code == 201, on_run.text


def test_regressed_questions_are_computed_by_the_server_from_a_bare_use_case(server, support):
    _, http = server
    editor = _headers(server, "mallory", {"support": "edit"})
    use_case = {
        "competency_questions": [
            {
                "id": "tickets-per-customer",
                "question": "Which tickets did a customer open?",
                "concepts": ["(Customer)-[OPENED]->(Ticket)"],
            }
        ]
    }

    posted = http.post(
        f"{API}/knowledge-graphs/support/use-case-versions",
        headers=editor,
        json={"use_case": use_case},
    )
    results = http.get(
        f"{API}/knowledge-graphs/support/ontology-versions/2/evaluations", headers=editor
    ).json()

    assert posted.status_code == 200, posted.text
    answerability = next(r for r in results if r["evaluator"] == "structural_answerability")
    assert answerability["metrics"]["regressed_questions"] == 1


def test_competency_question_coverage_is_computed_by_the_server(server, support):
    _, http = server
    editor = _headers(server, "mallory", {"support": "edit"})
    use_case = {
        "competency_questions": [
            {"id": "names", "question": "What are customers called?", "concepts": ["Customer.name"]}
        ]
    }
    forged = http.post(
        f"{API}/knowledge-graphs/support/ontology-versions/2/evaluations",
        headers=editor,
        json={"evaluator": "competency_question_coverage", "metrics": {"traced_concept_ratio": 1}},
    )

    http.post(
        f"{API}/knowledge-graphs/support/use-case-versions",
        headers=editor,
        json={"use_case": use_case},
    )
    results = http.get(
        f"{API}/knowledge-graphs/support/ontology-versions/2/evaluations", headers=editor
    ).json()

    assert forged.status_code == 422
    coverage = next(r for r in results if r["evaluator"] == "competency_question_coverage")
    # v2: Customer, Customer.name, Ticket, Ticket.opened_at; only the first two are traced.
    assert coverage["metrics"]["traced_concept_ratio"] == 0.5
    assert sorted(d["item"] for d in coverage["details"]) == ["Ticket", "Ticket.opened_at"]


def test_missing_definitions_are_computed_by_the_server(server, support):
    _, http = server
    editor = _headers(server, "mallory", {"support": "edit"})

    forged = http.post(
        f"{API}/knowledge-graphs/support/ontology-versions/2/evaluations",
        headers=editor,
        json={"evaluator": "definitions", "metrics": {"concepts_without_definition": 0}},
    )
    results = http.get(
        f"{API}/knowledge-graphs/support/ontology-versions/2/evaluations", headers=editor
    ).json()

    assert forged.status_code == 422
    definitions = next(r for r in results if r["evaluator"] == "definitions")
    # v2: only Ticket has a Definition; Customer, Customer.name and Ticket.opened_at lack one.
    assert definitions["metrics"]["concepts_without_definition"] == 3
    assert definitions["metrics"]["definition_ratio"] == 0.25


# --- Origin of hand registrations ------------------------------------------------------


def test_a_registered_ontology_is_always_of_origin_registered(server, support):
    _, http = server
    editor = _headers(server, "mallory", {"support": "edit"})
    ontology = stetiq.ontology.parse_yaml(WITHOUT_OPENED.replace("A support request", "A request"))

    response = http.post(
        f"{API}/knowledge-graphs/support/ontology-versions",
        headers=editor,
        json={"ontology": stetiq.ontology.to_dict(ontology), "origin": "run"},
    )

    assert response.status_code == 200, response.text
    assert response.json()["origin"] == "registered"


# --- Unknown and unauthorised ids look alike -------------------------------------------


@pytest.mark.parametrize(
    "path",
    [
        "/runs/{run}",
        "/runs/{run}/evaluate",
        "/observations/{observation}",
    ],
)
def test_ids_outside_the_tokens_grants_answer_like_unknown_ids(
    server, admin, support, support_ontology, path
):
    _, http = server
    admin.create_knowledge_graph("billing", ontology=support_ontology)
    outsider = _headers(server, "eve", {"billing": "edit"})
    run = admin.list_runs(support)[-1]
    method = "POST" if path.endswith("evaluate") else "GET"

    unknown_id = "0" * 32
    existing = http.request(
        method, API + path.format(run=run.id, observation=run.observation_id), headers=outsider
    )
    unknown = http.request(
        method, API + path.format(run=unknown_id, observation=unknown_id), headers=outsider
    )

    assert existing.status_code == unknown.status_code == 404
    existing_text = existing.text.replace(run.id, unknown_id).replace(
        run.observation_id, unknown_id
    )
    assert existing_text == unknown.text
