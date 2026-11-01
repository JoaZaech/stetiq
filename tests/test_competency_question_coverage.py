"""The `competency_question_coverage` Evaluator: which Concepts the Use Case's Competency
Questions reference, and which no question needs."""

import pytest

import stetiq

ONTOLOGY = """
node_types:
  - label: Customer
    properties:
      - {name: name, type: STRING, required: true}
      - {name: segment, type: STRING}
  - label: Ticket
    properties:
      - {name: opened_at, type: DATE}
  - label: Agent
relationship_types:
  - label: OPENED
    properties:
      - {name: channel, type: STRING}
  - label: ASSIGNED_TO
patterns:
  - [Customer, OPENED, Ticket]
  - [Ticket, ASSIGNED_TO, Agent]
"""

USE_CASE = """
competency_questions:
  - id: tickets-per-customer
    question: Which tickets did a given customer open?
    query: >
      MATCH (c:Customer {name: $name})-[:OPENED]->(t:Ticket)
      RETURN t.opened_at
  - id: customer-names
    question: What are our customers called?
    concepts: [Customer.name]
"""

COVERAGE = "competency_question_coverage"


@pytest.fixture
def kg(client):
    return client.create_knowledge_graph("support", ontology=ONTOLOGY)


def coverage(results):
    return {r.evaluator: r for r in results}.get(COVERAGE)


def untraced(result):
    return {d.item: d for d in result.details}


def test_a_new_version_reports_the_concepts_no_competency_question_references(client, kg):
    client.register_use_case(kg.name, USE_CASE)

    version = client.register_ontology(kg.name, ONTOLOGY + "  - [Agent, OPENED, Ticket]\n")

    result = coverage(client.get_evaluation_results(kg.name, version.number))
    assert result.use_case_version == 1
    assert result.metrics == {
        "concepts": 9,
        "traced_concepts": 5,
        "untraced_concepts": 4,
        "traced_concept_ratio": 5 / 9,
    }
    assert sorted(untraced(result)) == [
        "ASSIGNED_TO",
        "Agent",
        "Customer.segment",
        "OPENED.channel",
    ]
    detail = untraced(result)["Customer.segment"]
    assert detail.metric == "untraced_concepts"
    assert detail.data == {"kind": "property"}


DEPRECATING = """
node_types:
  - label: Customer
    properties:
      - {name: name, type: STRING, required: true}
      - {name: segment, type: STRING, deprecated: true, deprecationReason: unused}
  - label: Ticket
    properties:
      - {name: opened_at, type: DATE}
  - label: Agent
    deprecated: true
    properties:
      - {name: email, type: STRING}
relationship_types:
  - label: OPENED
    properties:
      - {name: channel, type: STRING}
  - label: ASSIGNED_TO
    replacedBy: OPENED
patterns:
  - [Customer, OPENED, Ticket]
  - [Ticket, ASSIGNED_TO, Agent]
"""


def test_deprecated_concepts_are_left_out_of_coverage(client, kg):
    client.register_use_case(kg.name, USE_CASE)

    version = client.register_ontology(kg.name, DEPRECATING)

    result = coverage(client.get_evaluation_results(kg.name, version.number))
    assert result.metrics == {
        "concepts": 6,
        "traced_concepts": 5,
        "untraced_concepts": 1,
        "traced_concept_ratio": 5 / 6,
    }
    assert list(untraced(result)) == ["OPENED.channel"]


def test_without_a_use_case_coverage_does_not_run(client, kg):
    version = client.register_ontology(kg.name, DEPRECATING)

    assert coverage(client.get_evaluation_results(kg.name, version.number)) is None
    assert coverage(client.evaluate(kg.name, version.number)) is None


def test_a_new_use_case_version_updates_coverage_without_re_registering_the_ontology(client, kg):
    client.register_use_case(kg.name, USE_CASE)

    client.add_competency_question(
        kg.name,
        stetiq.CompetencyQuestion(
            id="assignees",
            question="Who handles a ticket, and how was it opened?",
            concepts=("(Ticket)-[ASSIGNED_TO]->(Agent)", "OPENED.channel"),
        ),
    )

    result = coverage(client.get_evaluation_results(kg.name, 1))
    assert result.use_case_version == 2
    assert result.metrics["traced_concepts"] == 8
    assert list(untraced(result)) == ["Customer.segment"]
    assert [v.number for v in client.list_ontology_versions(kg.name)] == [1]


def test_an_attribute_named_on_a_subclass_traces_the_ancestor_that_declares_it(client):
    client.create_knowledge_graph(
        "parties",
        ontology="""
node_types:
  - label: Party
    properties: [{name: name, type: STRING}]
  - {label: Customer, parent: Party}
""",
    )

    client.register_use_case(
        "parties", [stetiq.CompetencyQuestion(id="q", question="?", concepts=("Customer.name",))]
    )

    result = coverage(client.get_evaluation_results("parties", 1))
    assert list(untraced(result)) == ["Party"]


def test_a_custom_evaluator_cannot_take_the_coverage_name(client, kg):
    # Recording a result under the name is refused too: see tests/test_server_trust.py.
    class Impostor(stetiq.OntologyVersionEvaluator):
        name = COVERAGE

        def evaluate(self, version):
            return stetiq.Evaluation(metrics={"traced_concept_ratio": 1.0})

    with pytest.raises(stetiq.EvaluatorError, match=COVERAGE):
        client.register_evaluator(Impostor())
    with pytest.raises(stetiq.EvaluatorError, match=COVERAGE):
        client.evaluate(kg.name, 1, evaluators=[Impostor()])
