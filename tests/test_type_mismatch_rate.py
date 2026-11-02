"""The type-mismatch Violation Rate, through the SDK, against the in-memory fake Graph Source.

The Observed Schema counts each property's values per type. The share of owners holding a
value of a non-conforming type is the `type_mismatch` Violation Rate, which Drift compares
with the Baseline Observation like any other Violation Rate.
"""

from dataclasses import replace
from datetime import date

import pytest

from stetiq.drift import DriftThresholds
from stetiq.graph_source import GraphSourceScope

BEFORE, AFTER = GraphSourceScope(database="neo4j"), GraphSourceScope(database="later")


@pytest.fixture
def support_kg(client, support_ontology):
    client.create_knowledge_graph("support", ontology=support_ontology)
    client.bind_graph_source("support", BEFORE)
    return "support"


def seed_tickets(graph_source, dated, as_strings, database="neo4j"):
    """`dated` Tickets with a DATE `opened_at` (as the support ontology declares) and
    `as_strings` with the date written as a string; one Customer opened the first."""
    customer = graph_source.add_node(["Customer"], {"name": "Ada"}, database=database)
    tickets = [
        graph_source.add_node(["Ticket"], {"opened_at": date(2026, 1, 1)}, database=database)
        for _ in range(dated)
    ]
    for _ in range(as_strings):
        graph_source.add_node(["Ticket"], {"opened_at": "2026-01-01"}, database=database)
    graph_source.add_relationship(customer, "OPENED", tickets[0])


def observe_in(client, kg, scope, **kw):
    client.bind_graph_source(kg, scope)
    return client.observe(kg, **kw)


def type_mismatch_findings(outcome):
    if outcome.drift is None:
        return []
    return [
        (f.subject, f.baseline_rate, f.observed_rate)
        for f in outcome.drift.findings
        if f.kind == "violation_increase" and f.violation == "type_mismatch"
    ]


def test_values_of_a_non_conforming_type_carry_their_share_as_the_violation_rate(
    client, support_kg, graph_source
):
    client.set_evolution_mode(support_kg, "strict")
    seed_tickets(graph_source, dated=98, as_strings=2)

    with client.start_run(support_kg) as run:
        pass

    [mismatch] = [
        m for m in client.get_run(run.id).conformance.mismatches if m.kind == "type_mismatch"
    ]
    assert (mismatch.subject, mismatch.rate) == ("Ticket.opened_at", 0.02)


def test_a_type_mismatch_rate_rising_beyond_the_threshold_since_the_baseline_is_drift(
    client, support_kg, graph_source
):
    seed_tickets(graph_source, dated=100, as_strings=0)
    seed_tickets(graph_source, dated=98, as_strings=2, database="later")  # +2 points

    observe_in(client, support_kg, BEFORE)
    outcome = observe_in(client, support_kg, AFTER)

    assert type_mismatch_findings(outcome) == [("Ticket.opened_at", 0.0, 0.02)]


def test_a_type_mismatch_rate_rising_within_the_threshold_is_not_drift(
    client, support_kg, graph_source
):
    seed_tickets(graph_source, dated=100, as_strings=0)
    seed_tickets(graph_source, dated=98, as_strings=2, database="later")

    observe_in(client, support_kg, BEFORE)
    outcome = observe_in(
        client, support_kg, AFTER, thresholds=DriftThresholds(max_violation_increase=0.02)
    )

    assert type_mismatch_findings(outcome) == []


class CountlessGraphSource:
    """A Graph Source that does not count values per type, as an older or third-party
    adapter: its Observed Schema has no `type_counts`."""

    def __init__(self, inner):
        self._inner = inner

    def observe(self, scope, *args, **kwargs):
        schema = self._inner.observe(scope, *args, **kwargs)

        def countless(owners):
            return tuple(
                replace(o, properties=tuple(replace(p, type_counts=None) for p in o.properties))
                for o in owners
            )

        return replace(
            schema,
            node_types=countless(schema.node_types),
            relationship_types=countless(schema.relationship_types),
        )


def not_comparable(outcome):
    return [
        (str(e.check), e.violation, e.subject, e.subject_kind)
        for e in outcome.observation.not_comparable
    ]


def test_an_observed_schema_without_counts_per_type_is_not_comparable(
    client_factory, support_ontology, graph_source
):
    client = client_factory(graph_source=CountlessGraphSource(graph_source))
    client.create_knowledge_graph("support", ontology=support_ontology)
    seed_tickets(graph_source, dated=100, as_strings=0)
    seed_tickets(graph_source, dated=50, as_strings=50, database="later")

    observe_in(client, "support", BEFORE)
    outcome = observe_in(client, "support", AFTER)

    assert type_mismatch_findings(outcome) == []
    assert not_comparable(outcome) == [
        ("violation_increase", "type_mismatch", "Ticket.opened_at", "property")
    ]
    assert client.get_observation(outcome.observation.id) == outcome.observation


def test_a_baseline_without_counts_per_type_is_not_comparable(
    client_factory, support_ontology, graph_source
):
    countless = client_factory(graph_source=CountlessGraphSource(graph_source))
    countless.create_knowledge_graph("support", ontology=support_ontology)
    seed_tickets(graph_source, dated=99, as_strings=1)
    seed_tickets(graph_source, dated=50, as_strings=50, database="later")

    observe_in(countless, "support", BEFORE)  # the baseline, stored without counts
    outcome = observe_in(client_factory(), "support", AFTER)

    assert type_mismatch_findings(outcome) == []
    assert not_comparable(outcome) == [
        ("violation_increase", "type_mismatch", "Ticket.opened_at", "property")
    ]
