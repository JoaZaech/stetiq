"""The `definitions` Evaluator: which Concepts and Vocabulary Values lack a Definition."""

import pytest

import stetiq

ONTOLOGY = """
vocabularies:
  - label: Status
    values:
      - {label: open, definition: Not started yet}
      - in_progress
      - {label: done, replacedBy: closed}
      - {label: stale, deprecated: true}
      - closed
node_types:
  - label: WorkOrder
    definition: A unit of maintenance work on one Machine
    properties:
      - {name: status, type: STRING, vocabulary: Status, definition: Where the work stands}
      - {name: opened_at, type: DATE}
      - {name: legacy_code, type: STRING, deprecated: true}
  - label: Machine
  - label: Line
    deprecated: true
    properties:
      - {name: name, type: STRING}
relationship_types:
  - label: PERFORMED_ON
    definition: The Machine the work is carried out on
  - label: RUNS_ON
    replacedBy: PERFORMED_ON
patterns:
  - [WorkOrder, PERFORMED_ON, Machine]
  - [Machine, RUNS_ON, Line]
"""

DEFINITIONS = "definitions"


@pytest.fixture
def kg(client):
    return client.create_knowledge_graph("plant", ontology=ONTOLOGY)


def definitions(results):
    return {r.evaluator: r for r in results}.get(DEFINITIONS)


def undocumented(result):
    return {d.item: d for d in result.details}


def test_a_new_version_reports_the_concepts_and_values_without_a_definition(client, kg):
    result = definitions(client.get_evaluation_results(kg.name, 1))

    # Counted: WorkOrder, WorkOrder.status, WorkOrder.opened_at, Machine, PERFORMED_ON
    # (Line, its attribute, RUNS_ON and WorkOrder.legacy_code are deprecated), and the
    # values open, in_progress and closed (done and stale are deprecated).
    assert result.metrics == {
        "concepts_without_definition": 2,
        "vocabulary_values_without_definition": 2,
        "definition_ratio": 4 / 8,
    }
    assert sorted(undocumented(result)) == [
        "Machine",
        "Status.closed",
        "Status.in_progress",
        "WorkOrder.opened_at",
    ]
    attribute = undocumented(result)["WorkOrder.opened_at"]
    assert attribute.metric == "concepts_without_definition"
    assert attribute.data == {"kind": "property"}
    assert undocumented(result)["Machine"].data == {"kind": "node_type"}
    value = undocumented(result)["Status.closed"]
    assert value.metric == "vocabulary_values_without_definition"
    assert value.data == {"kind": "vocabulary_value"}


def test_deprecating_the_undocumented_items_leaves_nothing_to_report(client, kg):
    version = client.register_ontology(
        kg.name,
        ONTOLOGY.replace("      - in_progress", "      - {label: in_progress, deprecated: true}")
        .replace("      - closed", "      - {label: closed, deprecated: true}")
        .replace(
            "{name: opened_at, type: DATE}", "{name: opened_at, type: DATE, replacedBy: status}"
        )
        .replace("  - label: Machine", "  - label: Machine\n    deprecated: true"),
    )

    result = definitions(client.get_evaluation_results(kg.name, version.number))
    assert result.metrics == {
        "concepts_without_definition": 0,
        "vocabulary_values_without_definition": 0,
        "definition_ratio": 1.0,
    }
    assert not result.details


def test_an_ontology_with_nothing_to_define_has_a_definition_ratio_of_one(client):
    client.create_knowledge_graph(
        "retired", ontology="node_types:\n  - {label: Legacy, deprecated: true}\n"
    )

    result = definitions(client.get_evaluation_results("retired", 1))
    assert result.metrics["definition_ratio"] == 1.0


ALL_CONCEPTS_DEFINED = """
gates:
  - name: concepts-documented
    check: metric
    evaluator: definitions
    metric: concepts_without_definition
    max: 0
"""


def test_a_gate_on_concepts_without_definition_fails_until_every_concept_has_one(client, kg):
    documented = client.register_ontology(
        kg.name,
        ONTOLOGY.replace(
            "{name: opened_at, type: DATE}", "{name: opened_at, type: DATE, definition: Reported}"
        ).replace("  - label: Machine", "  - label: Machine\n    definition: A piece of equipment"),
    )

    failing = client.evaluate_gates(kg.name, ALL_CONCEPTS_DEFINED, version=1)
    passing = client.evaluate_gates(kg.name, ALL_CONCEPTS_DEFINED, version=documented.number)

    assert not failing.passed
    assert "definitions.concepts_without_definition = 2 > max 0" in failing.failed[0].reasons[0]
    assert passing.passed


def test_a_custom_evaluator_cannot_take_the_definitions_name(client, kg):
    # Recording a result under the name is refused too: see tests/test_server_trust.py.
    class Impostor(stetiq.OntologyVersionEvaluator):
        name = DEFINITIONS

        def evaluate(self, version):
            return stetiq.Evaluation(metrics={"definition_ratio": 1.0})

    with pytest.raises(stetiq.EvaluatorError, match=DEFINITIONS):
        client.register_evaluator(Impostor())
    with pytest.raises(stetiq.EvaluatorError, match=DEFINITIONS):
        client.evaluate(kg.name, 1, evaluators=[Impostor()])
