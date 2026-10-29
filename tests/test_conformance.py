"""Conformance of a run's Observed Schema to its Declared Ontology, Evolution Mode and
Candidates, through the SDK, against the in-memory fake Graph Source."""

from datetime import date

import pytest

import stetiq
from stetiq.graph_source import GraphSourceScope


@pytest.fixture
def support_kg(client, support_ontology):
    client.create_knowledge_graph("support", ontology=support_ontology)
    client.bind_graph_source("support", GraphSourceScope(database="neo4j"))
    return "support"


def seed_conforming_graph(graph_source):
    """Exactly the support ontology: Customer(name)-[OPENED]->Ticket(opened_at)."""
    ada = graph_source.add_node(["Customer"], {"name": "Ada"})
    ticket = graph_source.add_node(["Ticket"], {"opened_at": date(2026, 1, 1)})
    graph_source.add_relationship(ada, "OPENED", ticket)
    return ada, ticket


def run_once(client, kg, version=1):
    with client.start_run(kg, ontology_version=version) as run:
        pass
    return client.get_run(run.id)


def test_a_run_whose_graph_matches_its_declared_ontology_fully_conforms(
    client, support_kg, graph_source
):
    seed_conforming_graph(graph_source)

    run = run_once(client, support_kg)

    assert run.status == "finished"
    assert run.conformance.score == 1.0
    assert run.conformance.mismatches == ()


def subjects(mismatches):
    return [m.subject for m in mismatches]


def test_the_breakdown_lists_declared_but_absent_and_present_but_undeclared_concepts(
    client, support_kg, graph_source
):
    graph_source.add_node(["Customer"], {"name": "Ada"})
    graph_source.add_node(["Agent"], {"name": "Grace"})

    run = run_once(client, support_kg)

    assert subjects(run.conformance.declared_absent) == [
        "Ticket",
        "Ticket.opened_at",
        "OPENED",
    ]
    assert subjects(run.conformance.undeclared) == ["Agent", "Agent.name"]
    assert subjects(run.conformance.pattern_mismatches) == [
        "(Customer)-[OPENED]->(Ticket)"
    ]
    # Elements: 6 declared (Customer, Customer.name, Ticket, Ticket.opened_at, OPENED, the
    # pattern) + 2 undeclared (Agent, Agent.name); only Customer and Customer.name conform.
    assert run.conformance.score == 0.25


def test_the_breakdown_lists_property_type_and_required_mismatches(
    client, support_kg, graph_source
):
    ada = graph_source.add_node(["Customer"], {"name": "Ada"})
    graph_source.add_node(["Customer"], {})  # `name` is required
    ticket = graph_source.add_node(
        ["Ticket"], {"opened_at": "yesterday"}
    )  # declared DATE
    graph_source.add_relationship(ada, "OPENED", ticket)

    run = run_once(client, support_kg)

    assert [
        (m.subject, m.kind, m.detail) for m in run.conformance.property_mismatches
    ] == [
        (
            "Customer.name",
            "required_missing",
            "required, but filled on 50% of Customer",
        ),
        ("Ticket.opened_at", "type_mismatch", "declared DATE, observed STRING"),
    ]
    assert run.conformance.declared_absent == ()
    assert run.conformance.undeclared == ()
    # 6 declared elements, all present; the two properties do not conform.
    assert run.conformance.score == pytest.approx(4 / 6)


WIDENING_ONTOLOGY = """
node_types:
  - label: Measurement
    properties:
      - {name: value, type: FLOAT}
"""


def test_integer_values_conform_to_a_declared_float(client, graph_source):
    client.create_knowledge_graph("metrics", ontology=WIDENING_ONTOLOGY)
    client.bind_graph_source("metrics", GraphSourceScope(database="neo4j"))
    graph_source.add_node(["Measurement"], {"value": 3})
    graph_source.add_node(["Measurement"], {"value": 2.5})

    run = run_once(client, "metrics")

    assert run.conformance.score == 1.0


# --- Evolution Mode -----------------------------------------------------------------


def test_evolution_mode_defaults_to_evolving(client, support_kg):
    assert client.get_evolution_mode(support_kg) == "evolving"


def test_evolution_mode_can_be_set_per_knowledge_graph(
    client, support_kg, support_ontology
):
    client.create_knowledge_graph("other", ontology=support_ontology)

    client.set_evolution_mode(support_kg, "strict")

    assert client.get_evolution_mode(support_kg) == "strict"
    assert client.get_evolution_mode("other") == "evolving"
    client.set_evolution_mode(support_kg, "evolving")
    assert client.get_evolution_mode(support_kg) == "evolving"


def test_an_unknown_evolution_mode_is_rejected(client, support_kg):
    with pytest.raises(ValueError):
        client.set_evolution_mode(support_kg, "lenient")


def test_evolution_mode_of_an_unknown_knowledge_graph_is_not_found(client):
    with pytest.raises(stetiq.NotFoundError):
        client.set_evolution_mode("nope", "strict")
    with pytest.raises(stetiq.NotFoundError):
        client.get_evolution_mode("nope")


def seed_graph_with_new_concepts(graph_source):
    """The support graph plus an Agent node type, a HANDLES relationship type and a
    Ticket.priority property, none of them declared."""
    ada, ticket = seed_conforming_graph(graph_source)
    graph_source.add_node(["Ticket"], {"opened_at": date(2026, 1, 2), "priority": 2})
    grace = graph_source.add_node(["Agent"], {"name": "Grace"})
    graph_source.add_relationship(grace, "HANDLES", ticket)


def test_strict_mode_fails_a_run_that_introduces_undeclared_concepts(
    client, support_kg, graph_source
):
    client.set_evolution_mode(support_kg, "strict")
    seed_graph_with_new_concepts(graph_source)

    run = run_once(client, support_kg)

    assert run.status == "failed"
    assert subjects(run.conformance.undeclared) == [
        "Agent",
        "Agent.name",
        "Ticket.priority",
        "HANDLES",
    ]
    assert client.get_observation(run.observation_id).run_id == run.id
    assert run.candidate_version is None
    assert [v.number for v in client.list_ontology_versions(support_kg)] == [1]


def test_ending_a_strict_run_returns_it_failed(client, support_kg, graph_source):
    client.set_evolution_mode(support_kg, "strict")
    seed_graph_with_new_concepts(graph_source)
    run = client.start_run(support_kg, ontology_version=1)

    assert run.end().status == "failed"


def test_strict_mode_finishes_a_run_whose_graph_only_lacks_declared_concepts(
    client, support_kg, graph_source
):
    client.set_evolution_mode(support_kg, "strict")
    graph_source.add_node(["Customer"], {"name": "Ada"})

    run = run_once(client, support_kg)

    assert run.status == "finished"
    assert subjects(run.conformance.declared_absent) == [
        "Ticket",
        "Ticket.opened_at",
        "OPENED",
    ]


CANDIDATE_ONTOLOGY = """
node_types:
  - label: Agent
    properties:
      - {name: name, type: STRING}
  - label: Customer
    properties:
      - {name: name, type: STRING, required: true}
  - label: Ticket
    description: A support request
    properties:
      - {name: opened_at, type: DATE}
      - {name: priority, type: INTEGER}
relationship_types: [HANDLES, OPENED]
patterns:
  - [Agent, HANDLES, Ticket]
  - [Customer, OPENED, Ticket]
"""


def test_evolving_mode_creates_a_candidate_of_the_declared_ontology_plus_new_concepts(
    client, support_kg, graph_source
):
    seed_graph_with_new_concepts(graph_source)

    run = run_once(client, support_kg)

    assert run.status == "finished"
    assert run.candidate_version == 2
    candidate = client.get_ontology_version(support_kg, 2)
    assert candidate.origin == "run"
    assert client.diff_ontologies(CANDIDATE_ONTOLOGY, candidate.ontology).changes == ()


def test_a_candidate_only_adds_to_the_declared_ontology(
    client, support_kg, graph_source
):
    seed_graph_with_new_concepts(graph_source)

    run = run_once(client, support_kg)

    diff = client.diff_ontology_versions(support_kg, 1, run.candidate_version)
    assert diff.classification == "additive"


def test_a_candidate_is_evaluated_by_the_built_in_evaluators(client, support_kg, graph_source):
    seed_graph_with_new_concepts(graph_source)

    run = run_once(client, support_kg)

    assert client.get_evaluation_results(support_kg, run.candidate_version) != []


def test_a_candidate_is_linked_to_the_run_that_produced_it(
    client_factory, support_kg, graph_source
):
    seed_graph_with_new_concepts(graph_source)
    run = run_once(client_factory(), support_kg)

    other = client_factory()

    assert other.get_run(run.id).candidate_version == 2
    assert [r.candidate_version for r in other.list_runs(support_kg)] == [2]


def test_a_conforming_run_creates_no_candidate(client, support_kg, graph_source):
    seed_conforming_graph(graph_source)

    run = run_once(client, support_kg)

    assert run.candidate_version is None
    assert [v.number for v in client.list_ontology_versions(support_kg)] == [1]


def test_an_undeclared_pattern_between_declared_concepts_is_no_new_concept(
    client, support_kg, graph_source
):
    ada, ticket = seed_conforming_graph(graph_source)
    graph_source.add_relationship(
        ticket, "OPENED", ada
    )  # (Ticket)-[OPENED]->(Customer)

    evolving = run_once(client, support_kg)
    client.set_evolution_mode(support_kg, "strict")
    strict = run_once(client, support_kg)

    assert subjects(evolving.conformance.pattern_mismatches) == [
        "(Ticket)-[OPENED]->(Customer)"
    ]
    assert evolving.candidate_version is None
    assert strict.status == "finished"


def test_a_crashed_run_creates_no_candidate(client, support_kg, graph_source):
    seed_graph_with_new_concepts(graph_source)

    with pytest.raises(RuntimeError):
        with client.start_run(support_kg, ontology_version=1) as run:
            raise RuntimeError("extraction crashed")

    assert client.get_run(run.id).status == "failed"
    assert client.get_run(run.id).candidate_version is None
    assert [v.number for v in client.list_ontology_versions(support_kg)] == [1]


def test_runs_producing_the_same_candidate_share_its_version(
    client, support_kg, graph_source
):
    seed_graph_with_new_concepts(graph_source)

    first = run_once(client, support_kg)
    second = run_once(client, support_kg)

    assert first.candidate_version == second.candidate_version == 2
