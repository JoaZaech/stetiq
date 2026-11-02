"""The run context: what a pipeline gets from stetiq before it extracts (the Ontology
Version to extract against, the latest Use Case Version, that version's evaluation
results and the executed Competency Questions of the latest finished run on it)."""

import json

import pytest
from fastapi.testclient import TestClient

import stetiq
from stetiq.auth import TokenRegistry
from stetiq.graph_source import GraphSourceScope, InMemoryGraphSource
from stetiq.ontology import parse_dict
from stetiq.server import create_app
from stetiq.tracking import RemoteTrackingService

ONTOLOGY = """
node_types:
  - label: Machine
    properties:
      - {name: name, type: STRING}
  - label: WorkOrder
relationship_types:
  - label: PERFORMED_ON
patterns:
  - [WorkOrder, PERFORMED_ON, Machine]
"""

USE_CASE = """
consumers:
  - id: assistant
    name: Maintenance assistant
    tasks:
      - id: triage
        description: Triage breakdowns
        competency_questions: [orders-per-machine, machine-names]
  - id: review
    name: Weekly review
    tasks:
      - id: weekly
        description: Review the week
        competency_questions: [orders-per-machine]
competency_questions:
  - id: orders-per-machine
    question: Which work orders were performed on a machine?
    query: MATCH (w:WorkOrder)-[:PERFORMED_ON]->(m:Machine) RETURN m.name, count(w)
  - id: machine-names
    question: What are the machines called?
    query: MATCH (m:Machine) RETURN m.name
  - id: unused
    question: Nobody asks this yet
"""

ORDERS_QUERY = "MATCH (w:WorkOrder)-[:PERFORMED_ON]->(m:Machine) RETURN m.name, count(w)"
NAMES_QUERY = "MATCH (m:Machine) RETURN m.name"


@pytest.fixture
def plant(client):
    client.create_knowledge_graph("plant", ontology=ONTOLOGY)
    client.bind_graph_source("plant", GraphSourceScope(database="neo4j"))
    client.register_use_case("plant", USE_CASE)
    return "plant"


def finish_a_run(client, graph_source):
    """A run that builds the declared graph; `orders-per-machine` returns two rows and
    `machine-names` none."""
    machine = graph_source.add_node(["Machine"], {"name": "Press 7"})
    graph_source.add_relationship(graph_source.add_node(["WorkOrder"]), "PERFORMED_ON", machine)
    graph_source.add_query_result(ORDERS_QUERY, [{"m.name": "Press 7", "count(w)": 1}] * 2)
    graph_source.add_query_result(NAMES_QUERY, [])
    with client.start_run("plant") as run:
        pass
    return client.get_run(run.id)


def test_the_context_defaults_to_the_contract_version_and_the_latest_use_case_version(
    client, plant
):
    client.register_ontology("plant", ONTOLOGY + "  - [WorkOrder, PERFORMED_ON, WorkOrder]\n")

    context = client.run_context("plant")

    assert context.ontology_version.number == 1  # production, not the newer version 2
    assert context.use_case_version is not None
    assert context.use_case_version.number == 1
    assert {r.evaluator for r in context.evaluation_results} >= {
        "hierarchy",
        "structural_answerability",
    }
    assert all(r.subject_id == "1" for r in context.evaluation_results)
    assert context.run is None
    assert context.run_evaluation_results == ()


def test_the_context_can_name_another_ontology_version(client, plant):
    client.register_ontology("plant", ONTOLOGY + "  - [WorkOrder, PERFORMED_ON, WorkOrder]\n")

    context = client.run_context("plant", version=2)

    assert context.ontology_version.number == 2
    assert all(r.subject_id == "2" for r in context.evaluation_results)


def test_the_context_as_json_annotates_each_question_with_its_tasks_and_consumers(client, plant):
    data = json.loads(json.dumps(client.run_context("plant").to_dict()))

    assert data["knowledge_graph"] == "plant"
    assert data["ontology_version"]["number"] == 1
    # The stetiq YAML form: it parses back into the version's Ontology.
    ontology = parse_dict(data["ontology_version"]["ontology"])
    assert ontology == client.get_ontology_version("plant", 1).ontology
    assert data["use_case_version"]["number"] == 1
    assert [c["id"] for c in data["use_case_version"]["use_case"]["consumers"]] == [
        "assistant",
        "review",
    ]
    questions = {q["id"]: q for q in data["competency_questions"]}
    assert questions["orders-per-machine"] == {
        "id": "orders-per-machine",
        "question": "Which work orders were performed on a machine?",
        "serves": [
            {"consumer": "assistant", "task": "triage"},
            {"consumer": "review", "task": "weekly"},
        ],
        "execution": None,
    }
    assert questions["unused"]["serves"] == []
    assert {r["evaluator"] for r in data["evaluation_results"]} >= {"structural_answerability"}
    assert data["run"] is None


def test_the_context_carries_the_executed_questions_of_the_latest_finished_run(
    client, plant, graph_source
):
    run = finish_a_run(client, graph_source)

    context = client.run_context("plant")
    data = context.to_dict()

    assert context.run is not None and context.run.id == run.id
    assert "competency_question_execution" in {r.evaluator for r in context.run_evaluation_results}
    assert data["run"]["id"] == run.id
    assert {r["evaluator"] for r in data["run"]["evaluation_results"]} >= {
        "conformance",
        "competency_question_execution",
    }
    questions = {q["id"]: q for q in data["competency_questions"]}
    assert questions["orders-per-machine"]["execution"] == {"status": "passed", "rows": 2}
    assert questions["machine-names"]["execution"] == {"status": "failed", "rows": 0}
    assert questions["unused"]["execution"] is None  # no query, never executed


def test_a_run_standing_for_another_version_is_not_the_contexts_run(client, plant, graph_source):
    finish_a_run(client, graph_source)
    graph_source.add_node(["Shift"])  # the next run adds a Concept: Candidate v2
    with client.start_run("plant") as evolving:
        pass

    context = client.run_context("plant", version=2)

    assert client.get_run(evolving.id).candidate_version == 2
    assert context.run is not None and context.run.id == evolving.id


VOCABULARY_ONTOLOGY = """
node_types:
  - label: WorkOrder
    properties:
      - {name: status, type: STRING, vocabulary: Status}
vocabularies:
  - label: Status
    values:
      - open
      - {label: on_hold, deprecated: true}
"""


class QuotesTheGraph(stetiq.ConstructionRunEvaluator):
    """A custom run Evaluator whose details quote instance data, as one may."""

    name = "quotes_the_graph"

    def evaluate(self, run):
        return stetiq.Evaluation(
            metrics={"quoted": 1},
            details=[stetiq.Detail("Press 7", "seen in the graph", data={"value": "Press 7"})],
        )


def keys(value):
    if isinstance(value, dict):
        return set(value) | {k for v in value.values() for k in keys(v)}
    if isinstance(value, list):
        return {k for v in value for k in keys(v)}
    return set()


def test_the_context_carries_metrics_only_never_values_from_the_graph(client, graph_source):
    client.create_knowledge_graph("orders", ontology=VOCABULARY_ONTOLOGY)
    client.set_evolution_mode("orders", "strict")
    client.bind_graph_source("orders", GraphSourceScope(database="neo4j"))
    graph_source.add_node(["WorkOrder"], {"status": "open"})
    graph_source.add_node(["WorkOrder"], {"status": "on_hold"})  # deprecated: reported
    with client.start_run("orders") as run:
        pass
    client.evaluate_run(run.id, evaluators=[QuotesTheGraph()])
    recorded = client.get_run_evaluation_results(run.id)
    # The recorded results do quote observed values: the context must drop them.
    [conformance] = [r for r in recorded if r.evaluator == "conformance"]
    assert [d.data["value"] for d in conformance.details if d.data] == ["on_hold"]

    context = client.run_context("orders")
    data = context.to_dict()

    assert context.run is not None and context.run.id == run.id
    assert all(r.details == () for r in context.run_evaluation_results)
    assert all(r.details == () for r in context.evaluation_results)
    assert {r["evaluator"] for r in data["run"]["evaluation_results"]} >= {
        "conformance",
        "quotes_the_graph",
    }
    results = data["evaluation_results"] + data["run"]["evaluation_results"]
    assert all(r["details"] == [] for r in results)
    assert {"value", "count"}.isdisjoint(keys(data))
    assert "Press 7" not in json.dumps(data)


def test_without_a_use_case_the_context_has_none(client):
    client.create_knowledge_graph("bare", ontology=ONTOLOGY)

    data = client.run_context("bare").to_dict()

    assert data["use_case_version"] is None
    assert data["competency_questions"] == []


def test_an_unknown_ontology_version_is_not_found(client, plant):
    with pytest.raises(stetiq.NotFoundError):
        client.run_context("plant", version=9)


def test_a_read_token_is_enough_for_the_context(tmp_path):
    database_url = f"sqlite:///{tmp_path / 'server.db'}"
    tokens = TokenRegistry(database_url)
    _, editor = tokens.issue("ada", {"plant": "edit"})
    _, reader = tokens.issue("pipeline", {"plant": "read"})
    graph_source = InMemoryGraphSource()
    with TestClient(create_app(database_url=database_url)) as http:

        def client_with(token):
            return stetiq.Client(
                str(http.base_url),
                service=RemoteTrackingService(str(http.base_url), http=http, token=token),
                graph_source=graph_source,
            )

        owner = client_with(editor)
        owner.create_knowledge_graph("plant", ontology=ONTOLOGY)
        owner.bind_graph_source("plant", GraphSourceScope(database="neo4j"))
        owner.register_use_case("plant", USE_CASE)
        finish_a_run(owner, graph_source)

        context = client_with(reader).run_context("plant")

    assert context.ontology_version.number == 1
    assert context.run is not None
