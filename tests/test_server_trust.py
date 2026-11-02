"""What the stetiq server must not take on the client's word.

A token with edit permission can send any request body, not only what the SDK sends.
These tests talk HTTP to the server directly, the way such a client would.
"""

import pytest
from fastapi.testclient import TestClient

import stetiq
from stetiq.auth import TokenRegistry
from stetiq.gates import gate_from_dict
from stetiq.graph_source import InMemoryGraphSource
from stetiq.server import create_app
from stetiq.tracking import RemoteTrackingService, codec, wire

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


def test_gate_previews_are_computed_by_the_server_for_a_reader_and_never_recorded(
    server, admin, support
):
    _, http = server
    admin.evaluate_gates(support, [gate_from_dict(NO_BREAKING)], version=2)
    [recorded] = admin.list_gate_results(support)
    reader = _headers(server, "rita", {"support": "read"})

    response = http.get(f"{API}/knowledge-graphs/support/gate-previews", headers=reader)

    assert response.status_code == 200, response.text
    [preview] = response.json()
    # The run consumed v1, the Contract Alias's version: no breaking change to find.
    assert preview["subject_kind"] == "construction_run"
    assert preview["subject_id"] == _run_id(admin, support)
    assert (preview["ontology_version"], preview["passed"]) == (1, True)
    assert preview["source"] == {
        "subject_kind": "ontology_version",
        "subject_id": "2",
        "evaluated_at": recorded.evaluated_at.isoformat(),
    }
    assert admin.list_gate_results(support) == [recorded]
    admin.set_alias(support, "staging", 1)
    assert admin.list_promotions(support)[-1].gate_result is None


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


# --- Consumer Gate results are computed by the server ------------------------------------

GATED_USE_CASE = {
    "competency_questions": [
        {"id": "customers", "question": "Which customers are there?", "query": "MATCH (c) RETURN c"}
    ],
    "consumers": [
        {
            "id": "triage-bot",
            "name": "Triage bot",
            "tasks": [
                {
                    "id": "route",
                    "description": "Route a ticket",
                    "competency_questions": ["customers"],
                }
            ],
            "consumer_gates": [{"check": "row_count_drop", "task": "route", "max_drop": 0.1}],
        }
    ],
}


@pytest.mark.parametrize(
    "smuggled",
    [
        {"consumer_gates": [{"check": "row_count_drop", "task": "route", "max_drop": 1.0}]},
        {"outcomes": [{"passed": True, "reasons": [], "findings": []}]},
        {"passed": True},
    ],
)
def test_a_consumer_gate_request_cannot_carry_definitions_or_outcomes(
    server, admin, support, smuggled
):
    _, http = server
    admin.register_use_case(support, GATED_USE_CASE)
    editor = _headers(server, "mallory", {"support": "edit"})

    response = http.post(
        f"{API}/knowledge-graphs/support/consumer-gate-results",
        headers=editor,
        json={"run": _run_id(admin, support), **smuggled},
    )

    assert response.status_code == 422
    assert admin.list_consumer_gate_results(support) == []


def test_a_consumer_gate_verdict_is_the_servers_own(server, admin, support):
    _, http = server
    admin.register_use_case(support, GATED_USE_CASE)
    editor = _headers(server, "mallory", {"support": "edit"})

    response = http.post(
        f"{API}/knowledge-graphs/support/consumer-gate-results", headers=editor, json={}
    )

    # The run executed no question (it predates the Use Case) and has no baseline.
    assert response.status_code == 201, response.text
    [result] = admin.list_consumer_gate_results(support)
    assert not result.passed and result.baseline_run_id is None


def test_a_consumer_gate_run_from_another_knowledge_graph_is_refused(
    server, admin, support, support_ontology
):
    _, http = server
    admin.register_use_case(support, GATED_USE_CASE)
    admin.create_knowledge_graph("billing", ontology=support_ontology)
    admin.bind_graph_source("billing", stetiq.GraphSourceScope(database="neo4j"))
    with admin.start_run("billing") as billing_run:
        pass
    editor = _headers(server, "mallory", {"support": "edit", "billing": "edit"})

    response = http.post(
        f"{API}/knowledge-graphs/support/consumer-gate-results",
        headers=editor,
        json={"run": billing_run.id},
    )

    assert response.status_code == 404
    assert admin.list_consumer_gate_results(support) == []


def test_consumer_gate_results_need_edit_to_record_and_read_to_list(server, admin, support):
    _, http = server
    admin.register_use_case(support, GATED_USE_CASE)
    reader = _headers(server, "rita", {"support": "read"})
    path = f"{API}/knowledge-graphs/support/consumer-gate-results"

    assert http.post(path, headers=reader, json={}).status_code == 403
    assert http.get(path, headers=reader).status_code == 200


# --- Proposed Definitions are applied by the server, to what the Candidate adds ----------


def _end_body(admin, kg, *nodes):
    graph = InMemoryGraphSource()
    for labels in nodes:
        graph.add_node(labels)
    scope = admin.get_graph_source(kg)
    return {
        "scope": codec.graph_source_scope_to_json(scope),
        "observed_schema": codec.observed_schema_to_json(graph.observe(scope)),
    }


def test_proposed_definitions_never_redefine_a_declared_concept(server, admin, support):
    _, http = server
    editor = _headers(server, "mallory", {"support": "edit"})
    run = admin.start_run("support", ontology_version=1)
    body = _end_body(admin, "support", ["Ticket"], ["Agent"])
    body["definitions"] = {"Ticket": "rewritten by the client", "Agent": "Who handles tickets"}

    response = http.post(f"{API}/runs/{run.id}/end", json=body, headers=editor)

    assert response.status_code == 200
    ended = response.json()
    assert ended["ignored_definitions"] == ["Ticket"]
    candidate = admin.get_ontology_version("support", ended["candidate_version"]).ontology
    assert candidate.node_type("Ticket").definition == "A support request"
    assert candidate.node_type("Agent").definition == "Who handles tickets"


@pytest.mark.parametrize(
    "definitions", [{"Agent": ""}, {"Agent": 3}, {"(A)-[R]->(B)": "a path"}, ["Agent"]]
)
def test_malformed_proposed_definitions_are_refused_and_the_run_keeps_running(
    server, admin, support, definitions
):
    _, http = server
    editor = _headers(server, "mallory", {"support": "edit"})
    run = admin.start_run("support", ontology_version=1)
    body = _end_body(admin, "support", ["Agent"])
    body["definitions"] = definitions

    response = http.post(f"{API}/runs/{run.id}/end", json=body, headers=editor)

    assert response.status_code == 422
    assert admin.get_run(run.id).status == "running"


def test_ending_an_ended_run_is_not_active_before_its_proposals_are_judged(server, admin, support):
    _, http = server
    editor = _headers(server, "mallory", {"support": "edit"})
    body = _end_body(admin, "support", ["Agent"])
    body["definitions"] = {"Agent": ""}

    response = http.post(f"{API}/runs/{_run_id(admin, 'support')}/end", json=body, headers=editor)

    assert response.status_code == 409
    assert response.json()["error"]["type"] == "RunNotActiveError"
