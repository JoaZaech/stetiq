"""Coverage Drift through the SDK, against the in-memory fake Graph Source.

A declared pattern's Coverage is the share of its endpoint nodes with at least one such
relationship: for out-degree, the source nodes; for in-degree, the target nodes. Drift
compares it with its value in the Baseline Observation, and only when
`max_coverage_drop` is set.
"""

import dataclasses

import pytest

from stetiq.drift import DriftThresholds, thresholds_from_config
from stetiq.graph_source import GraphSourceScope

BEFORE, AFTER = GraphSourceScope(database="neo4j"), GraphSourceScope(database="later")

PLANT = """
node_types:
  - label: WorkOrder
  - label: Machine
relationship_types:
  - label: ASSIGNED_TO
patterns:
  - [WorkOrder, ASSIGNED_TO, Machine]
"""

COVERAGE = DriftThresholds(max_coverage_drop=0.05)


@pytest.fixture
def plant(client):
    client.create_knowledge_graph("plant", ontology=PLANT)
    return client


def seed_work_orders(graph_source, on_a_machine, without, database="neo4j", machines=1):
    """`on_a_machine` WorkOrders on the first of `machines` Machines, `without` on none."""
    serving = [graph_source.add_node(["Machine"], {}, database=database) for _ in range(machines)]
    for _ in range(on_a_machine):
        order = graph_source.add_node(["WorkOrder"], {}, database=database)
        graph_source.add_relationship(order, "ASSIGNED_TO", serving[0])
    for _ in range(without):
        graph_source.add_node(["WorkOrder"], {}, database=database)


def observe_in(client, scope, **kw):
    client.bind_graph_source("plant", scope)
    return client.observe("plant", **kw)


def coverage_findings(outcome):
    if outcome.drift is None:
        return []
    return [
        (f.subject, f.subject_kind, f.direction, f.baseline_rate, f.observed_rate)
        for f in outcome.drift.findings
        if f.kind == "coverage_drop"
    ]


def test_coverage_falling_beyond_the_threshold_since_the_baseline_is_drift(plant, graph_source):
    seed_work_orders(graph_source, on_a_machine=19, without=1)  # 95% have a Machine
    seed_work_orders(graph_source, on_a_machine=17, without=3, database="later")  # 85%

    observe_in(plant, BEFORE, thresholds=COVERAGE)
    outcome = observe_in(plant, AFTER, thresholds=COVERAGE)

    [(subject, subject_kind, direction, baseline, observed)] = coverage_findings(outcome)
    assert (subject, subject_kind, direction) == (
        "(WorkOrder)-[ASSIGNED_TO]->(Machine)",
        "pattern",
        "out",
    )
    assert (baseline, observed) == (pytest.approx(0.95), pytest.approx(0.85))
    assert outcome.drift.thresholds.max_coverage_drop == 0.05
    assert plant.list_drift_events("plant") == [outcome.drift]


def test_coverage_falling_within_the_threshold_is_not_drift(plant, graph_source):
    seed_work_orders(graph_source, on_a_machine=19, without=1)  # 95%
    seed_work_orders(graph_source, on_a_machine=18, without=2, database="later")  # 90%

    observe_in(plant, BEFORE, thresholds=COVERAGE)
    outcome = observe_in(plant, AFTER, thresholds=COVERAGE)

    assert coverage_findings(outcome) == []  # exactly five points: not beyond the threshold


def test_in_degree_coverage_is_checked_over_the_target_nodes(plant, graph_source):
    seed_work_orders(graph_source, on_a_machine=10, without=0)  # 1 of 1 Machines used
    seed_work_orders(graph_source, on_a_machine=10, without=0, database="later", machines=2)

    observe_in(plant, BEFORE, thresholds=COVERAGE)
    outcome = observe_in(plant, AFTER, thresholds=COVERAGE)

    assert coverage_findings(outcome) == [
        ("(WorkOrder)-[ASSIGNED_TO]->(Machine)", "pattern", "in", 1.0, 0.5)
    ]


def test_coverage_is_not_checked_unless_max_coverage_drop_is_set(plant, graph_source):
    seed_work_orders(graph_source, on_a_machine=19, without=1)
    seed_work_orders(graph_source, on_a_machine=1, without=19, database="later")

    observe_in(plant, BEFORE)
    outcome = observe_in(plant, AFTER)

    assert coverage_findings(outcome) == []
    assert outcome.observation.not_comparable == ()


def seed_machines_at_a_site(graph_source, at_the_site, elsewhere, database="neo4j"):
    site = graph_source.add_node(["Site"], {}, database=database)
    for _ in range(at_the_site):
        machine = graph_source.add_node(["Machine"], {}, database=database)
        graph_source.add_relationship(machine, "AT", site)
    for _ in range(elsewhere):
        graph_source.add_node(["Machine"], {}, database=database)


def test_an_undeclared_pattern_is_never_checked(plant, graph_source):
    seed_machines_at_a_site(graph_source, at_the_site=10, elsewhere=0)
    seed_machines_at_a_site(graph_source, at_the_site=1, elsewhere=9, database="later")

    observe_in(plant, BEFORE, thresholds=COVERAGE)
    outcome = observe_in(plant, AFTER, thresholds=COVERAGE)

    assert coverage_findings(outcome) == []  # (Machine)-[AT]->(Site) is not declared
    assert outcome.observation.not_comparable == ()


class PredatingCoverage:
    """A Graph Source adapter written before Coverage: its degrees lack `with_edges`."""

    def __init__(self, source):
        self._source = source

    def observe(self, scope, *args, **kw):
        schema = self._source.observe(scope, *args, **kw)
        return dataclasses.replace(
            schema,
            patterns=tuple(
                dataclasses.replace(
                    p,
                    out_degree=dataclasses.replace(p.out_degree, with_edges=None),
                    in_degree=dataclasses.replace(p.in_degree, with_edges=None),
                )
                for p in schema.patterns
            ),
        )


def test_a_baseline_without_coverage_is_not_comparable(client_factory, graph_source):
    seed_work_orders(graph_source, on_a_machine=19, without=1)
    seed_work_orders(graph_source, on_a_machine=17, without=3, database="later")
    old = client_factory(graph_source=PredatingCoverage(graph_source))
    old.create_knowledge_graph("plant", ontology=PLANT)
    observe_in(old, BEFORE, thresholds=COVERAGE)

    outcome = observe_in(client_factory(), AFTER, thresholds=COVERAGE)

    assert coverage_findings(outcome) == []
    assert [
        (str(e.check), e.subject, e.subject_kind, e.reason)
        for e in outcome.observation.not_comparable
    ] == [
        (
            "coverage_drop",
            "(WorkOrder)-[ASSIGNED_TO]->(Machine)",
            "pattern",
            "no out-degree Coverage in the Baseline Observation",
        ),
        (
            "coverage_drop",
            "(WorkOrder)-[ASSIGNED_TO]->(Machine)",
            "pattern",
            "no in-degree Coverage in the Baseline Observation",
        ),
    ]


def test_max_coverage_drop_comes_from_the_drift_section_and_is_off_when_missing():
    assert thresholds_from_config({"drift": {"max_coverage_drop": 0.05}}).max_coverage_drop == 0.05
    assert thresholds_from_config({}).max_coverage_drop is None
    assert DriftThresholds().max_coverage_drop is None
