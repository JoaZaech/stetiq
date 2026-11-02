"""The `unjustified_additions` Evaluator: which Concepts an evolving run's Candidate adds
that no Competency Question of the latest Use Case Version needs. Driven as a pipeline
would: register a Use Case, run over the in-memory Graph Source, read the results."""

from datetime import date

import pytest

from stetiq.graph_source import GraphSourceScope

ONTOLOGY = """
node_types:
  - label: Component
    properties:
      - {name: name, type: STRING}
  - label: Machine
relationship_types:
  - label: PART_OF
patterns:
  - [Component, PART_OF, Machine]
"""
SHIFT = "  - label: Machine\n  - label: Shift\n"

EVALUATOR = "unjustified_additions"


@pytest.fixture
def plant(client):
    client.create_knowledge_graph("plant", ontology=ONTOLOGY)
    client.bind_graph_source("plant", GraphSourceScope(database="neo4j"))
    return "plant"


def use_case(*questions: str) -> str:
    return "competency_questions:\n" + "".join(questions)


SUPPLIERS_BY_QUERY = """
  - id: parts-suppliers
    question: Which suppliers' components keep failing?
    query: MATCH (c:Component)-[:SUPPLIED_BY]->(s:Supplier) RETURN s.name, count(c)
"""
SUPPLIERS_BY_MAPPING = """
  - id: parts-suppliers
    question: Which suppliers' components keep failing?
    concepts: [Supplier, SUPPLIED_BY]
"""
UNMAPPED = """
  - id: vague
    question: What is going on with suppliers and shifts?
"""
COMPONENTS = """
  - id: components
    question: Which components does a machine have?
    query: MATCH (c:Component)-[:PART_OF]->(m:Machine) RETURN c.name
"""


def seed_suppliers(graph_source, *, shift=False):
    """The declared graph, plus an undeclared Supplier(name, country) and SUPPLIED_BY;
    with `shift`, also an undeclared Shift(starts_at) nothing asks for."""
    machine = graph_source.add_node(["Machine"])
    component = graph_source.add_node(["Component"], {"name": "pump"})
    graph_source.add_relationship(component, "PART_OF", machine)
    supplier = graph_source.add_node(["Supplier"], {"name": "Acme", "country": "DE"})
    graph_source.add_relationship(component, "SUPPLIED_BY", supplier)
    if shift:
        graph_source.add_node(["Shift"], {"starts_at": date(2026, 1, 1)})


def run_once(client, kg):
    with client.start_run(kg) as run:
        pass
    return client.get_run(run.id)


def unjustified(client, kg, version):
    [result] = [r for r in client.get_evaluation_results(kg, version) if r.evaluator == EVALUATOR]
    return result


def items(result):
    return {d.item: d.data["kind"] for d in result.details}


def test_additions_a_question_needs_through_its_query_are_justified(client, plant, graph_source):
    client.register_use_case(plant, use_case(SUPPLIERS_BY_QUERY))
    seed_suppliers(graph_source)

    run = run_once(client, plant)

    result = unjustified(client, plant, run.candidate_version)
    # Supplier, SUPPLIED_BY, Supplier.name, Supplier.country: the Attributes ride on
    # the justified Supplier.
    assert result.metrics == {
        "unjustified_additions": 0,
        "added_concepts": 4,
        "justified_ratio": 1.0,
    }
    assert result.details == ()
    assert result.use_case_version == 1


def test_additions_a_question_needs_through_its_concept_mapping_are_justified(
    client, plant, graph_source
):
    client.register_use_case(plant, use_case(SUPPLIERS_BY_MAPPING))
    seed_suppliers(graph_source)

    run = run_once(client, plant)

    assert unjustified(client, plant, run.candidate_version).metrics["unjustified_additions"] == 0


def test_an_addition_nothing_needs_is_counted_and_listed(client, plant, graph_source):
    client.register_use_case(plant, use_case(SUPPLIERS_BY_QUERY))
    seed_suppliers(graph_source, shift=True)

    run = run_once(client, plant)

    result = unjustified(client, plant, run.candidate_version)
    assert result.metrics == {
        "unjustified_additions": 2,
        "added_concepts": 6,
        "justified_ratio": 4 / 6,
    }
    assert items(result) == {"Shift": "node_type", "Shift.starts_at": "property"}
    assert {d.metric for d in result.details} == {"unjustified_additions"}


def test_an_attribute_added_to_a_declared_concept_needs_a_question_of_its_own(
    client, plant, graph_source
):
    client.register_use_case(plant, use_case(COMPONENTS))
    graph_source.add_node(["Component"], {"name": "pump", "weight": 3})
    graph_source.add_node(["Component"], {"name": "valve", "serial": "x1"})
    client.register_use_case(  # Use Case Version 2 adds a question needing the weight
        plant,
        use_case(
            COMPONENTS,
            """
  - id: heavy
    question: Which components are heavy?
    concepts: [Component.weight]
""",
        ),
    )

    run = run_once(client, plant)

    result = unjustified(client, plant, run.candidate_version)
    assert result.use_case_version == 2  # the latest
    assert items(result) == {"Component.serial": "property"}


def test_an_unmapped_question_justifies_nothing(client, plant, graph_source):
    client.register_use_case(plant, use_case(UNMAPPED))
    seed_suppliers(graph_source)

    run = run_once(client, plant)

    result = unjustified(client, plant, run.candidate_version)
    assert items(result) == {
        "Supplier": "node_type",
        "Supplier.country": "property",
        "Supplier.name": "property",
        "SUPPLIED_BY": "relationship_type",
    }


def test_without_a_use_case_every_addition_is_unjustified(client, plant, graph_source):
    seed_suppliers(graph_source)

    run = run_once(client, plant)

    result = unjustified(client, plant, run.candidate_version)
    assert result.metrics["unjustified_additions"] == 4
    assert result.use_case_version is None


def test_added_vocabulary_values_are_left_out(client, graph_source):
    client.create_knowledge_graph(
        "orders",
        ontology="""
node_types:
  - label: Order
    properties:
      - {name: status, type: STRING, vocabulary: Status}
vocabularies:
  - label: Status
    values: [open, closed]
""",
    )
    client.bind_graph_source("orders", GraphSourceScope(database="neo4j"))
    graph_source.add_node(["Order"], {"status": "on_hold"})  # appended to Status

    run = run_once(client, "orders")

    assert run.candidate_version == 2
    assert unjustified(client, "orders", 2).metrics == {
        "unjustified_additions": 0,
        "added_concepts": 0,
        "justified_ratio": 1.0,
    }


def test_a_version_that_is_not_a_candidate_reports_no_additions(client, plant):
    client.register_use_case(plant, use_case(COMPONENTS))

    # A registered version adding Shift, which no question needs: not a run's extension.
    registered = client.register_ontology(plant, ONTOLOGY.replace("  - label: Machine\n", SHIFT))

    for version in (1, registered.number):
        assert unjustified(client, plant, version).metrics == {
            "unjustified_additions": 0,
            "added_concepts": 0,
            "justified_ratio": 1.0,
        }


GATE = """
gates:
  - name: no-unjustified-additions
    check: metric
    evaluator: unjustified_additions
    metric: unjustified_additions
    max: 0
"""


def test_a_metric_gate_passes_an_extension_a_question_asked_for(client, plant, graph_source):
    client.register_use_case(plant, use_case(SUPPLIERS_BY_QUERY))
    seed_suppliers(graph_source)
    run = run_once(client, plant)

    assert client.evaluate_gates(plant, GATE, run=run.id).passed


def test_a_metric_gate_fails_an_extension_nothing_asked_for(client, plant, graph_source):
    client.register_use_case(plant, use_case(SUPPLIERS_BY_QUERY))
    seed_suppliers(graph_source, shift=True)
    run = run_once(client, plant)

    result = client.evaluate_gates(plant, GATE, run=run.id)

    assert not result.passed
    reasons = result.failed[0].reasons
    assert reasons[0] == "unjustified_additions.unjustified_additions = 2 > max 0"
    assert any("Shift" in r for r in reasons[1:])


def test_a_metric_gate_passes_a_run_that_adds_nothing(client, plant, graph_source):
    client.register_use_case(plant, use_case(COMPONENTS))
    machine = graph_source.add_node(["Machine"])
    graph_source.add_relationship(
        graph_source.add_node(["Component"], {"name": "x"}), "PART_OF", machine
    )
    run = run_once(client, plant)

    assert run.candidate_version is None
    assert client.evaluate_gates(plant, GATE, run=run.id).passed
