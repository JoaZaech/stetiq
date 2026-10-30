"""Gold-ontology alignment: precision and recall over Concepts against a reference Ontology Version."""

import pytest

from stetiq.evaluation import GoldOntologyAlignment

# The reference ("gold") Ontology a researcher curated by hand.
GOLD = """
node_types:
  - label: Customer
    properties:
      - {name: name, type: STRING, required: true}
      - {name: email, type: STRING}
  - Ticket
  - Agent
relationship_types: [OPENED, ASSIGNED_TO]
patterns:
  - [Customer, OPENED, Ticket]
  - [Ticket, ASSIGNED_TO, Agent]
"""


@pytest.fixture
def gold(client):
    client.create_knowledge_graph("support-gold", ontology=GOLD)
    return client.get_ontology_version("support-gold", 1)


@pytest.fixture
def kg(client, support_ontology):
    return client.create_knowledge_graph("customer-support-kg", ontology=support_ontology)


def alignment(results):
    return [r for r in results if r.evaluator == "gold_alignment"]


def test_precision_and_recall_over_concepts_against_a_gold_ontology(client, kg, gold):
    results = client.evaluate(kg.name, 1, evaluators=[GoldOntologyAlignment(gold)])

    [result] = alignment(results)
    # Evaluated: Customer, Customer.name, Ticket, Ticket.opened_at, OPENED (5)
    # Gold: Customer, Customer.name, Customer.email, Ticket, Agent, OPENED, ASSIGNED_TO (7)
    # Matched: Customer, Customer.name, Ticket, OPENED (4)
    assert result.metrics["precision"] == pytest.approx(4 / 5)
    assert result.metrics["recall"] == pytest.approx(4 / 7)
    assert result.metrics["matched_concepts"] == 4
    assert result.metrics["unmatched_evaluated_concepts"] == 1
    assert result.metrics["unmatched_reference_concepts"] == 3
    by_metric = {}
    for d in result.details:
        by_metric.setdefault(d.metric, []).append(d.item)
    assert sorted(by_metric["matched_concepts"]) == [
        "Customer",
        "Customer.name",
        "OPENED",
        "Ticket",
    ]
    assert by_metric["unmatched_evaluated_concepts"] == ["Ticket.opened_at"]
    assert sorted(by_metric["unmatched_reference_concepts"]) == [
        "ASSIGNED_TO",
        "Agent",
        "Customer.email",
    ]


def test_the_reference_is_chosen_per_evaluation_and_recorded_with_each_result(
    client_factory, kg, gold
):
    client = client_factory()
    # A second reference: the evaluated version's own Ontology is a perfect match.
    own = client.get_ontology_version(kg.name, 1)

    client.evaluate(kg.name, 1, evaluators=[GoldOntologyAlignment(gold)])
    client.evaluate(kg.name, 1, evaluators=[GoldOntologyAlignment(own)])

    # Both results are kept side by side, visible to any client, each naming its reference.
    results = alignment(client_factory().get_evaluation_results(kg.name, 1))
    by_reference = {
        (r.parameters["reference_knowledge_graph"], r.parameters["reference_version"]): r
        for r in results
    }
    assert set(by_reference) == {("support-gold", 1), ("customer-support-kg", 1)}
    assert by_reference[("support-gold", 1)].metrics["recall"] == pytest.approx(4 / 7)
    perfect = by_reference[("customer-support-kg", 1)].metrics
    assert (perfect["precision"], perfect["recall"], perfect["f1"]) == (1.0, 1.0, 1.0)


def test_re_evaluating_against_the_same_reference_replaces_the_latest_result(client, kg, gold):
    client.evaluate(kg.name, 1, evaluators=[GoldOntologyAlignment(gold)])
    results = client.evaluate(kg.name, 1, evaluators=[GoldOntologyAlignment(gold)])

    assert len(alignment(results)) == 1


def test_parameterless_evaluators_record_empty_parameters(client, kg):
    results = client.get_evaluation_results(kg.name, 1)

    assert results and all(r.parameters == {} for r in results)
