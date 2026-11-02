"""The Cardinality Violation Rate, through the SDK, against the in-memory fake Graph Source.

Observation hands the adapter the contract's declared Pattern bounds; the adapter counts
the endpoint nodes whose degree lies outside each one, and Conformance turns that count
into a Violation Rate (violating endpoint nodes / endpoint nodes). Drift compares it with
the Baseline Observation on the Pattern subject.
"""

import pytest

from stetiq.drift import DriftThresholds
from stetiq.graph_source import GraphSourceScope, InMemoryGraphSource

BEFORE, AFTER = GraphSourceScope(database="neo4j"), GraphSourceScope(database="later")
PERFORMED_ON = "(WorkOrder)-[PERFORMED_ON]->(Asset)"


def maintenance_ontology(cardinality="{out: {max: 1}}"):
    pattern = "{source: WorkOrder, relationship: PERFORMED_ON, target: Asset"
    pattern += f", cardinality: {cardinality}}}" if cardinality else "}"
    return (
        "node_types: [WorkOrder, Asset]\nrelationship_types: [PERFORMED_ON]\n"
        f"patterns:\n  - {pattern}\n"
    )


@pytest.fixture
def maintenance(client):
    client.create_knowledge_graph("maintenance", ontology=maintenance_ontology())
    client.bind_graph_source("maintenance", BEFORE)
    return "maintenance"


def seed_work_orders(graph_source, total, doubled, database="neo4j"):
    """`total` WorkOrders each PERFORMED_ON one Asset, `doubled` of them on two."""
    asset = graph_source.add_node(["Asset"], {}, database=database)
    for i in range(total):
        work_order = graph_source.add_node(["WorkOrder"], {}, database=database)
        graph_source.add_relationship(work_order, "PERFORMED_ON", asset)
        if i < doubled:
            graph_source.add_relationship(work_order, "PERFORMED_ON", asset)


def observe_in(client, kg, scope):
    client.bind_graph_source(kg, scope)
    return client.observe(kg)


def rate_findings(outcome):
    if outcome.drift is None:
        return []
    return [
        (f.violation, f.subject, f.subject_kind, f.direction, f.baseline_rate, f.observed_rate)
        for f in outcome.drift.findings
        if f.kind == "violation_increase"
    ]


# --- Conformance --------------------------------------------------------------------


def test_a_cardinality_violation_carries_its_violation_rate(client, maintenance, graph_source):
    client.set_evolution_mode(maintenance, "strict")
    seed_work_orders(graph_source, total=4, doubled=1)

    with client.start_run(maintenance) as run:
        pass

    [mismatch] = client.get_run(run.id).conformance.mismatches
    assert (mismatch.kind, mismatch.subject, mismatch.direction, mismatch.rate) == (
        "cardinality_violation",
        PERFORMED_ON,
        "out",
        0.25,
    )


def test_an_unobserved_pattern_violates_its_minimum_on_every_endpoint_node(client, graph_source):
    client.create_knowledge_graph("maintenance", ontology=maintenance_ontology("{out: {min: 1}}"))
    client.bind_graph_source("maintenance", BEFORE)
    client.set_evolution_mode("maintenance", "strict")
    graph_source.add_node(["WorkOrder"], {})
    graph_source.add_node(["Asset"], {})

    with client.start_run("maintenance") as run:
        pass

    mismatches = client.get_run(run.id).conformance.mismatches
    assert [(m.direction, m.rate) for m in mismatches if m.kind == "cardinality_violation"] == [
        ("out", 1.0)
    ]


# --- Drift --------------------------------------------------------------------------


def test_one_work_order_over_the_bound_among_a_thousand_is_not_drift(
    client, maintenance, graph_source
):
    seed_work_orders(graph_source, total=1000, doubled=0)
    seed_work_orders(graph_source, total=1000, doubled=1, database="later")

    observe_in(client, maintenance, BEFORE)
    outcome = observe_in(client, maintenance, AFTER)

    assert outcome.drift is None
    assert outcome.observation.not_comparable == ()


def test_five_percent_of_work_orders_over_the_bound_is_drift_on_the_pattern(
    client, maintenance, graph_source
):
    seed_work_orders(graph_source, total=100, doubled=0)
    seed_work_orders(graph_source, total=100, doubled=5, database="later")

    observe_in(client, maintenance, BEFORE)
    outcome = observe_in(client, maintenance, AFTER)

    assert rate_findings(outcome) == [
        ("cardinality_violation", PERFORMED_ON, "pattern", "out", 0.0, 0.05)
    ]
    assert client.list_drift_events(maintenance) == [outcome.drift]


def test_the_rate_compares_with_the_baseline_s_stored_count(client, maintenance, graph_source):
    seed_work_orders(graph_source, total=100, doubled=2)
    seed_work_orders(graph_source, total=100, doubled=4, database="later")

    observe_in(client, maintenance, BEFORE)
    outcome = observe_in(client, maintenance, AFTER)

    assert rate_findings(outcome) == [
        ("cardinality_violation", PERFORMED_ON, "pattern", "out", 0.02, 0.04)
    ]


class _BoundsIgnoringGraphSource(InMemoryGraphSource):
    """An adapter from before pattern bounds: it takes them but counts nothing."""

    def observe(self, scope, bound_attributes=(), *, value_cap=100, pattern_bounds=()):
        return super().observe(scope, bound_attributes, value_cap=value_cap)


def test_a_schema_without_the_counts_is_not_comparable(client_factory):
    graph_source = _BoundsIgnoringGraphSource()
    seed_work_orders(graph_source, total=100, doubled=1)
    seed_work_orders(graph_source, total=100, doubled=5, database="later")
    client = client_factory(graph_source=graph_source)
    client.create_knowledge_graph("maintenance", ontology=maintenance_ontology())
    client.bind_graph_source("maintenance", BEFORE)

    observe_in(client, "maintenance", BEFORE)
    outcome = observe_in(client, "maintenance", AFTER)

    assert rate_findings(outcome) == []
    assert [
        (str(e.check), e.violation, e.subject, e.subject_kind)
        for e in outcome.observation.not_comparable
    ] == [("violation_increase", "cardinality_violation", PERFORMED_ON, "pattern")]


class _PreBoundsGraphSource(InMemoryGraphSource):
    """An adapter whose `observe` predates pattern bounds altogether."""

    def observe(self, scope, bound_attributes=(), *, value_cap=100):
        return super().observe(scope, bound_attributes, value_cap=value_cap)


def test_without_declared_bounds_the_adapter_is_not_asked_to_count(client_factory):
    graph_source = _PreBoundsGraphSource()
    seed_work_orders(graph_source, total=3, doubled=1)
    client = client_factory(graph_source=graph_source)
    client.create_knowledge_graph("maintenance", ontology=maintenance_ontology(None))
    client.bind_graph_source("maintenance", BEFORE)

    outcome = client.observe("maintenance")

    assert outcome.drift is None


def test_min_count_floors_a_pattern_s_rate_by_its_endpoint_nodes_not_its_relationships(
    client, graph_source
):
    """Every one of 20 WorkOrders loses its Asset: the Pattern has no relationships left,
    but its source class still has 20 nodes, which reaches a `min_count` of 10."""
    client.create_knowledge_graph("maintenance", ontology=maintenance_ontology("{out: {min: 1}}"))
    seed_work_orders(graph_source, total=20, doubled=0)
    for _ in range(20):
        graph_source.add_node(["WorkOrder"], {}, database="later")
    graph_source.add_node(["Asset"], {}, database="later")
    thresholds = DriftThresholds(min_count=10)

    client.bind_graph_source("maintenance", BEFORE)
    client.observe("maintenance", thresholds=thresholds)
    client.bind_graph_source("maintenance", AFTER)
    outcome = client.observe("maintenance", thresholds=thresholds)

    assert rate_findings(outcome) == [
        ("cardinality_violation", PERFORMED_ON, "pattern", "out", 0.0, 1.0)
    ]
    assert [e.check for e in outcome.observation.not_comparable] == []
