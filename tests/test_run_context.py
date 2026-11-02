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
    consumer_gates:
      - name: weekly-rows-hold
        check: row_count_drop
        task: weekly
        max_drop: 0.10
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
    # Executed questions stay a status and a row count: their details are dropped.
    [execution] = [
        r
        for r in data["run"]["evaluation_results"]
        if r["evaluator"] == "competency_question_execution"
    ]
    assert execution["details"] == []


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


class VersionQuotesTheGraph(stetiq.OntologyVersionEvaluator):
    """A custom version Evaluator whose free-form details hold a graph value anyway."""

    name = "version_quotes_the_graph"

    def evaluate(self, version):
        return stetiq.Evaluation(
            metrics={"quoted": 1},
            details=[stetiq.Detail("Press 9", "remembered", data={"value": "Press 9"})],
        )


def keys(value):
    if isinstance(value, dict):
        return set(value) | {k for v in value.values() for k in keys(v)}
    if isinstance(value, list):
        return {k for v in value for k in keys(v)}
    return set()


def test_the_context_never_carries_values_from_the_graph(client, graph_source):
    client.create_knowledge_graph("orders", ontology=VOCABULARY_ONTOLOGY)
    client.set_evolution_mode("orders", "strict")
    client.bind_graph_source("orders", GraphSourceScope(database="neo4j"))
    graph_source.add_node(["WorkOrder"], {"status": "open"})
    graph_source.add_node(["WorkOrder"], {"status": "on_hold"})  # deprecated: reported
    with client.start_run("orders") as run:
        pass
    client.evaluate_run(run.id, evaluators=[QuotesTheGraph()])
    client.evaluate("orders", 1, evaluators=[VersionQuotesTheGraph()])
    recorded = client.get_run_evaluation_results(run.id)
    # The recorded results do quote observed values: the context must drop them.
    [conformance] = [r for r in recorded if r.evaluator == "conformance"]
    assert [d.data["value"] for d in conformance.details if d.data] == ["on_hold"]

    context = client.run_context("orders")
    data = context.to_dict()

    assert context.run is not None and context.run.id == run.id
    assert all(r.details == () for r in context.run_evaluation_results)
    assert {r["evaluator"] for r in data["run"]["evaluation_results"]} >= {
        "conformance",
        "observed_schema",
        "quotes_the_graph",
    }
    assert all(r["details"] == [] for r in data["run"]["evaluation_results"])
    [custom] = [
        r for r in data["evaluation_results"] if r["evaluator"] == "version_quotes_the_graph"
    ]
    assert custom["details"] == []
    assert {"value", "count"}.isdisjoint(keys(data))
    assert "Press 7" not in json.dumps(data)
    assert "Press 9" not in json.dumps(data)


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
        run = finish_a_run(owner, graph_source)
        owner.evaluate_gates("plant", NO_BREAKING, run=run.id)
        owner.evaluate_consumer_gates("plant", run=run.id)

        context = client_with(reader).run_context("plant")

    assert context.ontology_version.number == 1
    assert context.run is not None
    [definitions] = [r for r in context.evaluation_results if r.evaluator == "definitions"]
    assert definitions.details  # a reader sees what the version Evaluators found
    assert context.verdicts.gate_result is not None
    assert context.verdicts.consumer_gate_results["review"] is not None
    assert context.last_attempt is not None and context.last_attempt.run.id == run.id


def test_the_context_names_what_each_version_evaluator_found(client, plant, graph_source):
    finish_a_run(client, graph_source)
    graph_source.add_node(["Shift"])  # an evolving run adds a Concept no question needs
    with client.start_run("plant"):
        pass

    data = client.run_context("plant", version=2).to_dict()

    found = {
        r["evaluator"]: {(d["metric"], d["item"]) for d in r["details"]}
        for r in data["evaluation_results"]
    }
    assert ("unjustified_additions", "Shift") in found["unjustified_additions"]
    assert ("untraced_concepts", "Shift") in found["competency_question_coverage"]
    assert ("concepts_without_definition", "Machine") in found["definitions"]
    assert ("isolated_node_types", "Shift") in found["isolated_node_types"]
    assert ("orphan_node_types", "Shift") in found["orphan_concepts"]
    [answerability] = [
        r for r in data["evaluation_results"] if r["evaluator"] == "structural_answerability"
    ]
    assert {d["item"]: d["data"] for d in answerability["details"]}["machine-names"] == {
        "status": "answerable",
        "source": "query",
        "required": ["Machine", "Machine.name"],
        "missing": [],
    }


# --- Recorded verdicts --------------------------------------------------------------


NOT_EVALUATED = {"status": "not_evaluated"}


def test_without_a_recorded_gate_result_the_gate_result_is_not_evaluated(client, plant):
    data = client.run_context("plant").to_dict()

    assert data["gate_result"] == NOT_EVALUATED


NO_BREAKING = """
gates:
  - name: no-breaking-changes
    check: ontology_diff
    max_classification: deprecating
"""

STRICT_NO_BREAKING = """
gates:
  - name: only-cosmetic
    check: ontology_diff
    max_classification: cosmetic
"""


def test_the_context_carries_the_latest_gate_result_about_its_run(client, plant, graph_source):
    run = finish_a_run(client, graph_source)
    client.evaluate_gates("plant", STRICT_NO_BREAKING, run=run.id)
    client.evaluate_gates("plant", NO_BREAKING, run=run.id)
    client.evaluate_gates("plant", STRICT_NO_BREAKING, version=1)  # about the version: later

    gate_result = client.run_context("plant").to_dict()["gate_result"]

    assert gate_result["status"] == "passed"
    assert (gate_result["subject_kind"], gate_result["subject_id"]) == ("construction_run", run.id)
    [outcome] = gate_result["outcomes"]
    assert outcome["passed"] is True
    assert outcome["gate"] == {
        "name": "no-breaking-changes",
        "check": "ontology_diff",
        "max_classification": "deprecating",
    }


def test_without_one_about_its_run_the_gate_result_is_the_latest_about_its_version(client, plant):
    without_names = ONTOLOGY.replace("      - {name: name, type: STRING}\n", "")
    client.register_ontology("plant", without_names)  # v2: breaking
    client.evaluate_gates("plant", NO_BREAKING, version=1)
    client.evaluate_gates("plant", NO_BREAKING, version=2)  # about another version

    gate_result = client.run_context("plant").to_dict()["gate_result"]
    other = client.run_context("plant", version=2).to_dict()["gate_result"]

    assert gate_result["status"] == "passed"
    assert (gate_result["subject_kind"], gate_result["subject_id"]) == ("ontology_version", "1")
    assert other["status"] == "failed"
    assert other["subject_id"] == "2"


def test_a_gated_consumer_without_a_recorded_verdict_is_not_evaluated(client, plant, graph_source):
    finish_a_run(client, graph_source)

    data = client.run_context("plant").to_dict()

    # `review` declares a Consumer Gate; `assistant` declares none and is absent.
    assert data["consumer_gate_results"] == [{"consumer": "review", **NOT_EVALUATED}]


def test_the_context_carries_each_gated_consumers_latest_verdict_about_its_run(
    client, plant, graph_source
):
    finish_a_run(client, graph_source)  # baseline: two rows
    graph_source.add_query_result(ORDERS_QUERY, [{"m.name": "Press 7", "count(w)": 1}])
    with client.start_run("plant") as candidate:
        pass
    client.evaluate_consumer_gates("plant", run=candidate.id)

    [verdict] = client.run_context("plant").to_dict()["consumer_gate_results"]

    assert verdict["consumer"] == "review"
    assert verdict["status"] == "failed"
    assert verdict["run_id"] == candidate.id
    [outcome] = verdict["outcomes"]
    assert outcome["gate"]["name"] == "weekly-rows-hold"
    [finding] = outcome["findings"]
    assert finding == {
        "task": "weekly",
        "competency_question": "orders-per-machine",
        "limit": 0.1,
        "before": 2,
        "after": 1,
        "change": -0.5,
    }


def test_a_verdict_about_another_run_is_not_the_contexts(client, plant, graph_source):
    earlier = finish_a_run(client, graph_source)
    client.evaluate_consumer_gates("plant", run=earlier.id)
    finish_a_run(client, graph_source)  # the context's run: never evaluated

    data = client.run_context("plant").to_dict()

    assert data["consumer_gate_results"] == [{"consumer": "review", **NOT_EVALUATED}]


def test_reading_the_context_records_no_verdict(client, plant, graph_source):
    run = finish_a_run(client, graph_source)
    client.evaluate_gates("plant", NO_BREAKING, run=run.id)

    client.run_context("plant")
    client.run_context("plant", version=1)

    assert len(client.list_gate_results("plant")) == 1
    assert client.list_consumer_gate_results("plant") == []


QUOTED_STAYS_LOW = """
gates:
  - name: quotes-nothing
    check: metric
    evaluator: quotes_the_graph
    metric: quoted
    max: 0
"""


def test_a_recorded_gate_outcome_keeps_its_verdict_but_never_quotes_details(
    client, plant, graph_source
):
    run = finish_a_run(client, graph_source)
    client.evaluate_run(run.id, evaluators=[QuotesTheGraph()])
    recorded = client.evaluate_gates("plant", QUOTED_STAYS_LOW, run=run.id)
    # The recorded reasons do quote the custom Evaluator's details.
    assert any("Press 7" in r for r in recorded.outcomes[0].reasons)

    gate_result = client.run_context("plant").to_dict()["gate_result"]

    [outcome] = gate_result["outcomes"]
    assert gate_result["status"] == "failed"
    assert outcome["passed"] is False
    assert outcome["reasons"] == ["quotes_the_graph.quoted = 1 > max 0"]
    assert "Press 7" not in json.dumps(gate_result)


# --- The last attempt -----------------------------------------------------------------


def test_an_evolving_run_is_the_last_attempt_at_the_version_it_consumed(
    client, plant, graph_source
):
    finish_a_run(client, graph_source)
    graph_source.add_node(["Shift"])  # the next run adds a Concept: Candidate v2
    with client.start_run("plant") as evolving:
        pass

    context = client.run_context("plant")  # production: version 1
    data = context.to_dict()["last_attempt"]

    assert context.run is not None and context.run.id != evolving.id  # `run` stands for v1
    assert data["id"] == evolving.id
    assert data["status"] == "finished"
    assert data["ontology_version"] == 1
    assert data["candidate_version"] == 2
    assert data["added"]["classification"] == "additive"
    assert [(c["concept"], c["kind"]) for c in data["added"]["changes"]] == [("Shift", "added")]


def test_a_strict_failed_run_is_the_last_attempt_with_what_it_would_have_added(
    client, plant, graph_source
):
    client.set_evolution_mode("plant", "strict")
    finish_a_run(client, graph_source)
    graph_source.add_node(["Shift"])  # strict mode fails a run that adds a Concept
    with client.start_run("plant") as rejected:
        pass
    versions = len(client.list_ontology_versions("plant"))

    context = client.run_context("plant")
    data = context.to_dict()["last_attempt"]

    assert data["id"] == rejected.id
    assert data["status"] == "failed"
    assert data["candidate_version"] is None
    assert data["added"]["classification"] == "additive"
    assert [(c["concept"], c["kind"]) for c in data["added"]["changes"]] == [("Shift", "added")]
    assert context.run is not None and context.run.id != rejected.id  # `run` is unchanged
    assert len(client.list_ontology_versions("plant")) == versions  # nothing registered


def test_a_crashed_run_is_skipped_for_the_last_ended_one(client, plant, graph_source):
    ended = finish_a_run(client, graph_source)
    with pytest.raises(RuntimeError), client.start_run("plant"):
        raise RuntimeError("the pipeline crashed")

    data = client.run_context("plant").to_dict()["last_attempt"]

    assert data["id"] == ended.id
    assert data["status"] == "finished"
    assert data["added"] == {"classification": None, "changes": []}


def test_the_last_attempt_is_null_on_a_fresh_knowledge_graph(client, plant):
    assert client.run_context("plant").to_dict()["last_attempt"] is None


def test_the_last_attempt_carries_its_run_level_results_and_executed_questions(
    client, plant, graph_source
):
    finish_a_run(client, graph_source)
    graph_source.add_node(["Shift"])
    with client.start_run("plant") as evolving:
        pass

    data = client.run_context("plant").to_dict()["last_attempt"]

    assert data["id"] == evolving.id
    assert {r["evaluator"] for r in data["evaluation_results"]} >= {
        "conformance",
        "competency_question_execution",
    }
    assert all(r["details"] == [] for r in data["evaluation_results"])
    assert {q["id"]: (q["status"], q["rows"]) for q in data["competency_questions"]} == {
        "orders-per-machine": ("passed", 2),
        "machine-names": ("failed", 0),
    }


def test_the_last_attempts_verdicts_are_recorded_or_not_evaluated(client, plant, graph_source):
    finish_a_run(client, graph_source)
    graph_source.add_node(["Shift"])
    with client.start_run("plant") as evolving:
        pass

    before = client.run_context("plant").to_dict()["last_attempt"]
    client.evaluate_gates("plant", NO_BREAKING, run=evolving.id)
    client.evaluate_consumer_gates("plant", run=evolving.id)
    after = client.run_context("plant").to_dict()["last_attempt"]

    assert before["gate_result"] == NOT_EVALUATED
    assert before["consumer_gate_results"] == [{"consumer": "review", **NOT_EVALUATED}]
    assert after["gate_result"]["status"] == "passed"
    assert after["gate_result"]["subject_id"] == evolving.id
    [verdict] = after["consumer_gate_results"]
    assert verdict["consumer"] == "review"
    assert verdict["run_id"] == evolving.id
    assert verdict["status"] == "passed"


def test_a_strict_failed_attempt_never_borrows_its_versions_gate_result(
    client, plant, graph_source
):
    client.set_evolution_mode("plant", "strict")
    client.evaluate_gates("plant", NO_BREAKING, version=1)
    graph_source.add_node(["Shift"])
    with client.start_run("plant"):
        pass

    data = client.run_context("plant").to_dict()

    assert data["gate_result"]["status"] == "passed"  # about version 1
    assert data["last_attempt"]["gate_result"] == NOT_EVALUATED


def vocabulary_attempt(client, graph_source, mode):
    """A run against `orders` whose WorkOrder takes "Press 9", outside its Vocabulary, and
    adds a Shift node type."""
    client.create_knowledge_graph("orders", ontology=VOCABULARY_ONTOLOGY)
    client.set_evolution_mode("orders", mode)
    client.bind_graph_source("orders", GraphSourceScope(database="neo4j"))
    graph_source.add_node(["WorkOrder"], {"status": "open"})
    graph_source.add_node(["WorkOrder"], {"status": "Press 9"})
    graph_source.add_node(["Shift"])
    with client.start_run("orders") as run:
        pass
    return client.get_run(run.id)


def test_a_strict_failed_attempt_withholds_the_vocabulary_values_it_saw(client, graph_source):
    run = vocabulary_attempt(client, graph_source, "strict")

    data = client.run_context("orders").to_dict()

    assert run.status == "failed"
    attempt = data["last_attempt"]
    assert attempt["id"] == run.id
    # Values observed in the graph that never became Ontology (ADR 0010)...
    assert "Press 9" not in json.dumps(data)
    assert attempt["withheld_vocabulary_values"] == 1
    # ...while the Concepts it would have added stay.
    assert [c["concept"] for c in attempt["added"]["changes"]] == ["Shift"]


def test_an_evolving_attempt_keeps_the_vocabulary_values_its_candidate_added(client, graph_source):
    run = vocabulary_attempt(client, graph_source, "evolving")

    attempt = client.run_context("orders").to_dict()["last_attempt"]

    assert run.candidate_version is not None
    assert attempt["withheld_vocabulary_values"] == 0
    values = [c["value"] for c in attempt["added"]["changes"] if "value" in c]
    assert values == ["Press 9"]  # part of the registered Candidate's Ontology
