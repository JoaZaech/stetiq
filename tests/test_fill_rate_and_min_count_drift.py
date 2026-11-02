"""Fill-rate Drift, the `min_count` floor and pattern counts, through the SDK, against the
in-memory fake Graph Source.

A declared Attribute that isn't required has a fill rate (the share of its owners holding
it); Drift compares it with the Baseline Observation's. Pattern counts compare with the
previous Observation, like type counts. A type, pattern or owner below `min_count` is too
small to compare, so its statistical checks are not comparable instead.
"""

from datetime import date

import pytest

from stetiq import InvalidDriftConfigError
from stetiq.drift import DriftThresholds, thresholds_from_config
from stetiq.graph_source import GraphSourceScope

BEFORE, AFTER = GraphSourceScope(database="neo4j"), GraphSourceScope(database="later")
PATTERN = "(Customer)-[OPENED]->(Ticket)"


@pytest.fixture
def support_kg(client, support_ontology):
    client.create_knowledge_graph("support", ontology=support_ontology)
    client.bind_graph_source("support", BEFORE)
    return "support"


def seed_tickets(graph_source, dated, undated=0, database="neo4j"):
    """One Customer (named, as required) who opened `dated` Tickets holding their optional
    `opened_at` and `undated` Tickets without it."""
    ada = graph_source.add_node(["Customer"], {"name": "Ada"}, database=database)
    for props in [{"opened_at": date(2026, 1, 1)}] * dated + [{}] * undated:
        ticket = graph_source.add_node(["Ticket"], props, database=database)
        graph_source.add_relationship(ada, "OPENED", ticket)
    return ada


def observe_in(client, kg, scope, **kw):
    client.bind_graph_source(kg, scope)
    return client.observe(kg, **kw)


def findings(outcome, kind):
    if outcome.drift is None:
        return []
    return [f for f in outcome.drift.findings if f.kind == kind]


def gaps(outcome):
    return [(str(e.check), e.subject, e.reason) for e in outcome.observation.not_comparable]


# --- Fill rate ----------------------------------------------------------------------------


def test_an_optional_attribute_filled_less_than_at_the_baseline_is_drift(
    client, support_kg, graph_source
):
    fill = DriftThresholds(max_fill_rate_drop=0.1)
    seed_tickets(graph_source, dated=10)  # 100% filled
    seed_tickets(graph_source, dated=8, undated=2, database="later")  # 80%

    observe_in(client, support_kg, BEFORE, thresholds=fill)
    outcome = observe_in(client, support_kg, AFTER, thresholds=fill)

    [finding] = findings(outcome, "fill_rate_drop")
    assert (finding.subject, finding.subject_kind) == ("Ticket.opened_at", "property")
    assert (finding.baseline_rate, finding.observed_rate) == (1.0, 0.8)
    assert finding.detail == "fill rate fell from 100.0% to 80.0% since the Baseline Observation"
    assert outcome.drift.thresholds.max_fill_rate_drop == 0.1
    assert client.list_drift_events(support_kg)[-1] == outcome.drift


def test_a_required_attribute_never_gets_a_fill_rate_finding(client, support_kg, graph_source):
    fill = DriftThresholds(max_fill_rate_drop=0.1, max_violation_increase=None)
    seed_tickets(graph_source, dated=1)
    seed_tickets(graph_source, dated=1, database="later")
    graph_source.add_node(["Customer"], {}, database="later")  # half the Customers unnamed

    observe_in(client, support_kg, BEFORE, thresholds=fill)
    outcome = observe_in(client, support_kg, AFTER, thresholds=fill)

    assert findings(outcome, "fill_rate_drop") == []
    assert outcome.observation.not_comparable == ()


def test_a_fill_rate_drop_at_the_threshold_or_without_one_is_not_drift(
    client, support_kg, graph_source
):
    seed_tickets(graph_source, dated=10)
    seed_tickets(graph_source, dated=9, undated=1, database="later")  # exactly 10 points

    observe_in(client, support_kg, BEFORE, thresholds=DriftThresholds(max_fill_rate_drop=0.1))
    at_threshold = observe_in(
        client, support_kg, AFTER, thresholds=DriftThresholds(max_fill_rate_drop=0.1)
    )
    unset = observe_in(client, support_kg, AFTER)

    assert at_threshold.drift is None
    assert unset.drift is None


def test_an_optional_attribute_whose_owner_the_baseline_did_not_observe_is_not_comparable(
    client, support_kg, graph_source
):
    fill = DriftThresholds(max_fill_rate_drop=0.1)
    graph_source.add_node(["Customer"], {"name": "Ada"})  # no Tickets at the baseline
    seed_tickets(graph_source, dated=1, undated=1, database="later")

    observe_in(client, support_kg, BEFORE, thresholds=fill)
    outcome = observe_in(client, support_kg, AFTER, thresholds=fill)

    assert findings(outcome, "fill_rate_drop") == []
    assert gaps(outcome) == [
        ("fill_rate_drop", "Ticket.opened_at", "Ticket not observed in the Baseline Observation")
    ]


# --- Pattern counts -----------------------------------------------------------------------


def test_a_pattern_count_dropping_beyond_the_threshold_is_drift_on_the_pattern(
    client, support_kg, graph_source
):
    drop = DriftThresholds(max_count_drop=0.1)
    seed_tickets(graph_source, dated=10)
    ada = seed_tickets(graph_source, dated=5, database="later")
    for _ in range(5):  # as many Tickets and OPENED edges, but half run the other way
        ticket = graph_source.add_node(
            ["Ticket"], {"opened_at": date(2026, 1, 1)}, database="later"
        )
        graph_source.add_relationship(ticket, "OPENED", ada)

    observe_in(client, support_kg, BEFORE, thresholds=drop)
    outcome = observe_in(client, support_kg, AFTER, thresholds=drop)

    [finding] = findings(outcome, "count_drop")
    assert (finding.subject, finding.subject_kind) == (PATTERN, "pattern")
    assert (finding.previous_count, finding.observed_count) == (10, 5)


# --- min_count ----------------------------------------------------------------------------


def test_with_a_min_count_a_small_type_falling_raises_nothing_and_is_not_comparable(
    client, support_kg, graph_source
):
    small = DriftThresholds(max_count_drop=0.1, min_count=100)
    seed_tickets(graph_source, dated=3)
    seed_tickets(graph_source, dated=2, database="later")

    observe_in(client, support_kg, BEFORE, thresholds=small)
    outcome = observe_in(client, support_kg, AFTER, thresholds=small)

    assert outcome.drift is None
    below = "in the previous Observation, below min_count (100)"
    assert gaps(outcome) == [
        ("count_drop", "Customer", f"1 {below}"),
        ("count_drop", "Ticket", f"3 {below}"),
        ("count_drop", "OPENED", f"3 {below}"),
        ("count_drop", PATTERN, f"3 {below}"),
    ]


def test_a_min_count_of_zero_compares_every_type(client, support_kg, graph_source):
    drop = DriftThresholds(max_count_drop=0.1)
    seed_tickets(graph_source, dated=3)
    seed_tickets(graph_source, dated=2, database="later")

    observe_in(client, support_kg, BEFORE, thresholds=drop)
    outcome = observe_in(client, support_kg, AFTER, thresholds=drop)

    assert [f.subject for f in findings(outcome, "count_drop")] == ["Ticket", "OPENED", PATTERN]
    assert outcome.observation.not_comparable == ()


def test_an_owner_below_min_count_at_the_baseline_has_no_fill_rate_finding(
    client, support_kg, graph_source
):
    small = DriftThresholds(max_fill_rate_drop=0.1, min_count=100)
    seed_tickets(graph_source, dated=10)
    seed_tickets(graph_source, dated=8, undated=2, database="later")

    observe_in(client, support_kg, BEFORE, thresholds=small)
    outcome = observe_in(client, support_kg, AFTER, thresholds=small)

    assert outcome.drift is None
    assert gaps(outcome) == [
        (
            "fill_rate_drop",
            "Ticket.opened_at",
            "10 in the Baseline Observation, below min_count (100)",
        )
    ]


def test_an_owner_fallen_below_min_count_has_no_violation_rate_finding(
    client, support_kg, graph_source
):
    small = DriftThresholds(min_count=5)
    for _ in range(9):
        graph_source.add_node(["Customer"], {"name": "Ada"})
    graph_source.add_node(["Customer"], {})  # 10% unnamed
    graph_source.add_node(["Customer"], {"name": "Ada"}, database="later")
    graph_source.add_node(["Customer"], {}, database="later")  # 50% unnamed

    observe_in(client, support_kg, BEFORE, thresholds=small)
    outcome = observe_in(client, support_kg, AFTER, thresholds=small)

    assert findings(outcome, "violation_increase") == []
    assert [
        (str(e.check), e.violation, e.subject, e.reason) for e in outcome.observation.not_comparable
    ] == [
        (
            "violation_increase",
            "required_missing",
            "Customer.name",
            "2 in this Observation, below min_count (5)",
        )
    ]


# --- stetiq.yaml ----------------------------------------------------------------------------


def test_fill_rate_and_min_count_come_from_the_drift_section_of_the_repo_config():
    config = {"drift": {"max_fill_rate_drop": 0.05, "min_count": 100}}

    assert thresholds_from_config(config) == DriftThresholds(max_fill_rate_drop=0.05, min_count=100)


def test_without_the_keys_fill_rate_is_off_and_min_count_is_zero():
    thresholds = thresholds_from_config({"drift": {}})

    assert (thresholds.max_fill_rate_drop, thresholds.min_count) == (None, 0)


@pytest.mark.parametrize(
    "section",
    [
        {"max_fill_rate_drop": -0.1},
        {"max_fill_rate_drop": "10%"},
        {"min_count": -1},
        {"min_count": 1.5},
        {"min_count": True},
        {"min_count": None},
    ],
)
def test_a_malformed_fill_rate_or_min_count_is_rejected(section):
    with pytest.raises(InvalidDriftConfigError):
        thresholds_from_config({"drift": section})
