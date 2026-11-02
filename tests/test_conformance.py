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
    # Strict, so the undeclared Agent is judged against the Declared Ontology (an evolving
    # run would be judged against the Candidate that adds it).
    client.set_evolution_mode(support_kg, "strict")
    graph_source.add_node(["Customer"], {"name": "Ada"})
    graph_source.add_node(["Agent"], {"name": "Grace"})

    run = run_once(client, support_kg)

    assert subjects(run.conformance.declared_absent) == [
        "Ticket",
        "Ticket.opened_at",
        "OPENED",
    ]
    assert subjects(run.conformance.undeclared) == ["Agent", "Agent.name"]
    assert subjects(run.conformance.pattern_mismatches) == ["(Customer)-[OPENED]->(Ticket)"]
    # Elements: 6 declared (Customer, Customer.name, Ticket, Ticket.opened_at, OPENED, the
    # pattern) + 2 undeclared (Agent, Agent.name); only Customer and Customer.name conform.
    assert run.conformance.score == 0.25


def test_the_breakdown_lists_property_type_and_required_mismatches(
    client, support_kg, graph_source
):
    ada = graph_source.add_node(["Customer"], {"name": "Ada"})
    graph_source.add_node(["Customer"], {})  # `name` is required
    ticket = graph_source.add_node(["Ticket"], {"opened_at": "yesterday"})  # declared DATE
    graph_source.add_relationship(ada, "OPENED", ticket)

    run = run_once(client, support_kg)

    assert [(m.subject, m.kind, m.detail) for m in run.conformance.property_mismatches] == [
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


# Every WorkOrder is PERFORMED_ON exactly one Machine; a Machine has at most two WorkOrders.
CARDINALITY_ONTOLOGY = """
node_types: [WorkOrder, Machine]
relationship_types: [PERFORMED_ON]
patterns:
  - source: WorkOrder
    relationship: PERFORMED_ON
    target: Machine
    cardinality: {out: {min: 1, max: 1}, in: {max: 2}}
"""


@pytest.fixture
def maintenance_kg(client):
    client.create_knowledge_graph("maintenance", ontology=CARDINALITY_ONTOLOGY)
    client.bind_graph_source("maintenance", GraphSourceScope(database="neo4j"))
    return "maintenance"


def test_a_graph_within_the_declared_cardinality_conforms(client, maintenance_kg, graph_source):
    press, lathe = graph_source.add_node(["Machine"], {}), graph_source.add_node(["Machine"], {})
    for machine in (press, press, lathe):
        graph_source.add_relationship(
            graph_source.add_node(["WorkOrder"], {}), "PERFORMED_ON", machine
        )
    graph_source.add_node(["Machine"], {})  # in-degree 0 is within `in: {max: 2}`

    run = run_once(client, maintenance_kg)

    assert run.conformance.mismatches == ()
    assert run.conformance.score == 1.0


def test_out_and_in_degrees_outside_the_declared_cardinality_are_violations(
    client, maintenance_kg, graph_source
):
    press, lathe = graph_source.add_node(["Machine"], {}), graph_source.add_node(["Machine"], {})
    for _ in range(3):  # press gets three WorkOrders: in-degree 3 > max 2
        graph_source.add_relationship(
            graph_source.add_node(["WorkOrder"], {}), "PERFORMED_ON", press
        )
    on_both = graph_source.add_node(["WorkOrder"], {})  # out-degree 2 > max 1
    graph_source.add_relationship(on_both, "PERFORMED_ON", press)
    graph_source.add_relationship(on_both, "PERFORMED_ON", lathe)
    graph_source.add_node(["WorkOrder"], {})  # out-degree 0 < min 1

    run = run_once(client, maintenance_kg)

    assert [(m.subject, m.subject_kind, m.kind, m.detail) for m in run.conformance.mismatches] == [
        (
            "(WorkOrder)-[PERFORMED_ON]->(Machine)",
            "pattern",
            "cardinality_violation",
            "out-degree observed 0..2, declared min 1, max 1",
        ),
        (
            "(WorkOrder)-[PERFORMED_ON]->(Machine)",
            "pattern",
            "cardinality_violation",
            "in-degree observed 1..4, declared max 2",
        ),
    ]
    # Items: WorkOrder, Machine, PERFORMED_ON, the pattern, and its three bounds (out min,
    # out max, in max). All three bounds fail.
    assert run.conformance.score == 4 / 7


def test_each_cardinality_bound_counts_in_the_score(client, maintenance_kg, graph_source):
    press = graph_source.add_node(["Machine"], {})
    on_both = graph_source.add_node(["WorkOrder"], {})  # out-degree 2: only `max` fails
    graph_source.add_relationship(on_both, "PERFORMED_ON", press)
    graph_source.add_relationship(on_both, "PERFORMED_ON", graph_source.add_node(["Machine"], {}))

    run = run_once(client, maintenance_kg)

    assert [m.detail for m in run.conformance.mismatches] == [
        "out-degree observed 2..2, declared min 1, max 1"
    ]
    assert run.conformance.score == 6 / 7


def test_a_minimum_is_violated_when_the_pattern_is_never_observed(
    client, maintenance_kg, graph_source
):
    graph_source.add_node(["WorkOrder"], {})
    graph_source.add_node(["Machine"], {})

    run = run_once(client, maintenance_kg)

    assert [(m.kind, m.detail) for m in run.conformance.pattern_mismatches] == [
        ("absent", ""),
        ("cardinality_violation", "out-degree observed 0..0, declared min 1, max 1"),
    ]
    # PERFORMED_ON and the pattern are absent and `out min` fails; `out max` and `in max` hold.
    assert run.conformance.score == 4 / 7


# --- Evolution Mode -----------------------------------------------------------------


def test_evolution_mode_defaults_to_evolving(client, support_kg):
    assert client.get_evolution_mode(support_kg) == "evolving"


def test_evolution_mode_can_be_set_per_knowledge_graph(client, support_kg, support_ontology):
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
    _, ticket = seed_conforming_graph(graph_source)
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


def test_a_candidate_only_adds_to_the_declared_ontology(client, support_kg, graph_source):
    seed_graph_with_new_concepts(graph_source)

    run = run_once(client, support_kg)

    diff = client.diff_ontology_versions(support_kg, 1, run.candidate_version)
    assert diff.classification == "additive"


def test_a_candidate_keeps_the_declared_constraints(client, support_ontology, graph_source):
    constrained = support_ontology + (
        "constraints:\n  - {type: UNIQUENESS, node_type: Customer, property_name: name}\n"
    )
    client.create_knowledge_graph("support", ontology=constrained)
    client.bind_graph_source("support", GraphSourceScope(database="neo4j"))
    seed_graph_with_new_concepts(graph_source)

    run = run_once(client, "support")

    candidate = client.get_ontology_version("support", run.candidate_version).ontology
    assert [(c.node_type, c.property_name) for c in candidate.constraints] == [("Customer", "name")]


def test_a_candidate_keeps_the_declared_cardinality(client, maintenance_kg, graph_source):
    machine = graph_source.add_node(["Machine"], {})
    graph_source.add_relationship(graph_source.add_node(["WorkOrder"], {}), "PERFORMED_ON", machine)
    graph_source.add_node(["Technician"], {})  # a new Concept

    run = run_once(client, maintenance_kg)

    candidate = client.get_ontology_version(maintenance_kg, run.candidate_version).ontology
    assert [p.cardinality for p in candidate.patterns] == [
        {"out": {"min": 1, "max": 1}, "in": {"max": 2}}
    ]


HIERARCHY_ONTOLOGY = """
node_types:
  - label: Person
    properties:
      - {name: name, type: STRING, required: true}
  - label: Agent
    parent: Person
"""


def test_properties_inherited_from_a_parent_are_declared_on_the_subclass(client, graph_source):
    client.create_knowledge_graph("staff", ontology=HIERARCHY_ONTOLOGY)
    client.bind_graph_source("staff", GraphSourceScope(database="neo4j"))
    graph_source.add_node(["Person", "Agent"], {"name": "Grace"})

    run = run_once(client, "staff")

    assert run.conformance.mismatches == ()
    assert run.candidate_version is None


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
    graph_source.add_relationship(ticket, "OPENED", ada)  # (Ticket)-[OPENED]->(Customer)

    evolving = run_once(client, support_kg)
    client.set_evolution_mode(support_kg, "strict")
    strict = run_once(client, support_kg)

    assert subjects(evolving.conformance.pattern_mismatches) == ["(Ticket)-[OPENED]->(Customer)"]
    assert evolving.candidate_version is None
    assert strict.status == "finished"


def test_a_crashed_run_creates_no_candidate(client, support_kg, graph_source):
    seed_graph_with_new_concepts(graph_source)

    with pytest.raises(RuntimeError), client.start_run(support_kg, ontology_version=1) as run:
        raise RuntimeError("extraction crashed")

    assert client.get_run(run.id).status == "failed"
    assert client.get_run(run.id).candidate_version is None
    assert [v.number for v in client.list_ontology_versions(support_kg)] == [1]


def test_runs_producing_the_same_candidate_share_its_version(client, support_kg, graph_source):
    seed_graph_with_new_concepts(graph_source)

    first = run_once(client, support_kg)
    second = run_once(client, support_kg)

    assert first.candidate_version == second.candidate_version == 2


# --- Conformance of an evolving run: judged against the Candidate it gave rise to ---------


def conformance_result(client, run):
    [result] = [
        r for r in client.get_run_evaluation_results(run.id) if r.evaluator == "conformance"
    ]
    return result


def test_an_evolving_run_is_judged_against_its_candidate(client, support_kg, graph_source):
    seed_graph_with_new_concepts(graph_source)

    run = run_once(client, support_kg)

    # Agent, HANDLES (with their Attributes and pattern) and Ticket.priority are the
    # Candidate's additions, its Ontology Diff from version 1, not mismatches.
    assert run.candidate_version == 2
    assert run.conformance.mismatches == ()
    assert run.conformance.score == 1.0
    diff = client.diff_ontology_versions(support_kg, 1, run.candidate_version)
    assert {c.concept for c in diff.changes} == {"Agent", "HANDLES", "Ticket.priority"}


def test_the_conformance_run_result_and_gate_read_the_candidate_judgement(
    client, support_kg, graph_source
):
    seed_graph_with_new_concepts(graph_source)
    run = run_once(client, support_kg)

    gate = client.evaluate_gates(
        support_kg, "gates:\n  - {name: conforms, check: conformance, min_score: 1.0}\n", run=run.id
    )

    result = conformance_result(client, run)
    assert result.metrics["score"] == 1.0
    assert result.metrics["undeclared"] == 0
    assert gate.passed


def test_an_evolving_run_still_mismatches_what_its_candidate_does_not_absorb(
    client, support_kg, graph_source
):
    seed_graph_with_new_concepts(graph_source)
    graph_source.add_node(["Customer"], {})  # `name` is required

    run = run_once(client, support_kg)

    assert run.candidate_version == 2
    assert [(m.subject, m.kind) for m in run.conformance.mismatches] == [
        ("Customer.name", "required_missing")
    ]
    assert conformance_result(client, run).metrics["property_mismatches"] == 1


def test_an_evolving_run_with_appended_vocabulary_values_conforms_to_its_candidate(
    client, graph_source
):
    client.create_knowledge_graph("orders", ontology=STATUS_ONTOLOGY)
    client.bind_graph_source("orders", GraphSourceScope(database="neo4j"))
    graph_source.add_node(["Order"], {"status": "open"})
    graph_source.add_node(["Order"], {"status": "on_hold"})  # not a value of Status

    run = run_once(client, "orders")

    assert run.candidate_version == 2
    assert run.conformance.mismatches == ()


def test_a_strict_run_is_still_judged_against_its_declared_ontology(
    client, support_kg, graph_source
):
    client.set_evolution_mode(support_kg, "strict")
    seed_graph_with_new_concepts(graph_source)

    run = run_once(client, support_kg)

    assert run.status == "failed"
    assert "Agent" in subjects(run.conformance.undeclared)
    assert conformance_result(client, run).metrics["undeclared"] == 4


STATUS_ONTOLOGY = """
node_types:
  - label: Order
    properties:
      - {name: status, type: STRING, vocabulary: Status}
vocabularies:
  - label: Status
    values: [open, closed]
"""
