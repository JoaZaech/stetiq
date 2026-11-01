"""A Construction Run proposes Definitions for the Concepts it adds: `end_run` applies
them to the Concepts its Candidate adds, and lists every other proposal on the run as
ignored. Driven as an upstream pipeline would, over the in-memory Graph Source."""

import pytest

import stetiq
from stetiq.graph_source import GraphSourceScope

ONTOLOGY = """
node_types:
  - label: Component
    description: A part of a machine
    properties:
      - {name: name, type: STRING, description: What the part is called}
"""

SUPPLIER = "A company that supplies components"
SUPPLIED_BY = "Links a component to the company that supplied it"
SUPPLIER_NAME = "The supplier's registered name"


@pytest.fixture
def plant(client):
    client.create_knowledge_graph("plant", ontology=ONTOLOGY)
    client.bind_graph_source("plant", GraphSourceScope(database="neo4j"))
    return "plant"


def seed_suppliers(graph_source):
    component = graph_source.add_node(["Component"], {"name": "pump"})
    supplier = graph_source.add_node(["Supplier"], {"name": "Acme"})
    graph_source.add_relationship(component, "SUPPLIED_BY", supplier)


def definitions_result(client, kg, version):
    [result] = [
        r for r in client.get_evaluation_results(kg, version) if r.evaluator == "definitions"
    ]
    return result


def test_proposed_definitions_document_the_concepts_the_candidate_adds(client, plant, graph_source):
    seed_suppliers(graph_source)

    with client.start_run(plant) as run:
        run.propose_definitions({"Supplier": "draft", "SUPPLIED_BY": SUPPLIED_BY})
        run.propose_definitions({"Supplier": SUPPLIER, "Supplier.name": SUPPLIER_NAME})
    ended = client.get_run(run.id)

    candidate = client.get_ontology_version(plant, ended.candidate_version).ontology
    supplier = candidate.node_type("Supplier")
    assert supplier.definition == SUPPLIER  # the later call wins
    assert supplier.properties[0].definition == SUPPLIER_NAME
    assert candidate.relationship_type("SUPPLIED_BY").definition == SUPPLIED_BY
    assert ended.ignored_definitions == ()
    result = definitions_result(client, plant, ended.candidate_version)
    assert result.metrics["concepts_without_definition"] == 0


def test_proposals_for_concepts_the_run_did_not_add_are_ignored_and_listed(
    client, plant, graph_source
):
    seed_suppliers(graph_source)

    with client.start_run(plant) as run:
        run.propose_definitions(
            {
                "Supplier": SUPPLIER,
                "Component": "an attempt to redefine a declared Concept",
                "Component.name": "another",
                "Shift": "a Concept the run never added",
            }
        )
    ended = client.get_run(run.id)

    candidate = client.get_ontology_version(plant, ended.candidate_version).ontology
    assert candidate.node_type("Component").definition == "A part of a machine"
    assert candidate.node_type("Component").properties[0].definition == "What the part is called"
    assert candidate.node_type("Supplier").definition == SUPPLIER
    assert ended.ignored_definitions == ("Component", "Component.name", "Shift")


def test_a_strict_run_ignores_every_proposal(client, plant, graph_source):
    client.set_evolution_mode(plant, "strict")
    seed_suppliers(graph_source)

    with client.start_run(plant) as run:
        run.propose_definitions({"Supplier": SUPPLIER})
    ended = client.get_run(run.id)

    assert ended.status == "failed"
    assert ended.ignored_definitions == ("Supplier",)
    assert [v.number for v in client.list_ontology_versions(plant)] == [1]


def test_a_run_that_adds_nothing_ignores_every_proposal(client, plant, graph_source):
    graph_source.add_node(["Component"], {"name": "pump"})

    with client.start_run(plant) as run:
        run.propose_definitions({"Supplier": SUPPLIER})
    ended = client.get_run(run.id)

    assert ended.candidate_version is None
    assert ended.ignored_definitions == ("Supplier",)


def test_without_proposals_a_candidate_is_built_as_before(client, plant, graph_source):
    seed_suppliers(graph_source)

    with client.start_run(plant) as run:
        pass
    ended = client.get_run(run.id)

    candidate = client.get_ontology_version(plant, ended.candidate_version).ontology
    assert candidate.node_type("Supplier").definition is None
    assert ended.ignored_definitions == ()


def test_equal_proposals_give_the_same_candidate(client, plant, graph_source):
    seed_suppliers(graph_source)
    candidates = []
    for _ in range(2):
        with client.start_run(plant) as run:
            run.propose_definitions({"Supplier": SUPPLIER})
        candidates.append(client.get_run(run.id).candidate_version)

    with client.start_run(plant) as run:
        run.propose_definitions({"Supplier": "worded differently"})
    candidates.append(client.get_run(run.id).candidate_version)

    assert candidates == [2, 2, 3]


@pytest.mark.parametrize(
    "proposals",
    [
        {"Supplier": ""},
        {"Supplier": "   "},
        {"": SUPPLIER},
        {"(A)-[R]->(B)": SUPPLIER},
        {"Supplier": 3},
    ],
)
def test_a_malformed_proposal_is_refused_before_the_run_ends(client, plant, proposals):
    run = client.start_run(plant)

    with pytest.raises(stetiq.OntologyValidationError):
        run.propose_definitions(proposals)

    assert client.get_run(run.id).status == "running"
