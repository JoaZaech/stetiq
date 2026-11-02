"""New and persisting Drift findings, through the SDK, against the in-memory fake Graph
Source.

Each finding of an on-demand Observation is *new* or *persisting*, by comparison with the
previous Observation's findings (recomputed when that Observation raised no event; none
at all when it was judged against another Ontology Version). A rate finding persists only
while its rate has not worsened since the previous Observation.
"""

from datetime import date

import pytest

from stetiq.drift import DriftThresholds
from stetiq.graph_source import GraphSourceScope

FIRST, SECOND, THIRD = (GraphSourceScope(database=d) for d in ("first", "second", "third"))


@pytest.fixture
def support_kg(client, support_ontology):
    client.create_knowledge_graph("support", ontology=support_ontology)
    return "support"


def seed(graph_source, database, named=1, unnamed=0, agents=0):
    """The support ontology's graph: `named` Customers with their required `name`,
    `unnamed` without, one Ticket the first one opened, and `agents` undeclared Agents."""
    customers = [
        graph_source.add_node(["Customer"], {"name": "Ada"}, database=database)
        for _ in range(named)
    ]
    for _ in range(unnamed):
        graph_source.add_node(["Customer"], {}, database=database)
    ticket = graph_source.add_node(["Ticket"], {"opened_at": date(2026, 1, 1)}, database=database)
    graph_source.add_relationship(customers[0], "OPENED", ticket)
    for _ in range(agents):
        graph_source.add_node(["Agent"], {}, database=database)


def observe_in(client, kg, scope, **kw):
    client.bind_graph_source(kg, scope)
    return client.observe(kg, **kw)


def marks(outcome):
    """(kind, subject, new) per finding."""
    return [(f.kind, f.subject, f.new) for f in outcome.drift.findings]


def test_a_finding_the_previous_observation_also_raised_is_persisting(
    client, support_kg, graph_source
):
    seed(graph_source, "first", agents=1)
    seed(graph_source, "second", agents=1)

    first = observe_in(client, support_kg, FIRST)
    second = observe_in(client, support_kg, SECOND)

    assert marks(first) == [("undeclared", "Agent", True)]
    assert marks(second) == [("undeclared", "Agent", False)]
    assert client.list_drift_events(support_kg)[-1].findings[0].new is False


def test_a_finding_the_previous_observation_did_not_raise_is_new(client, support_kg, graph_source):
    seed(graph_source, "first")
    seed(graph_source, "second", agents=1)

    first = observe_in(client, support_kg, FIRST)
    second = observe_in(client, support_kg, SECOND)

    assert first.drift is None
    assert marks(second) == [("undeclared", "Agent", True)]


def test_the_findings_of_a_previous_observation_that_raised_no_event_are_recomputed(
    client, support_kg, graph_source
):
    """A run-end Observation is never checked for Drift, yet it saw the Agent too."""
    seed(graph_source, "first", agents=1)
    seed(graph_source, "second", agents=1)
    client.bind_graph_source(support_kg, FIRST)
    with client.start_run(support_kg):
        pass

    second = observe_in(client, support_kg, SECOND)

    assert marks(second) == [("undeclared", "Agent", False)]


FOURTH = GraphSourceScope(database="fourth")


def test_a_violation_rate_persists_until_it_worsens_again(client, support_kg, graph_source):
    seed(graph_source, "first", named=10)  # the baseline: every Customer named
    seed(graph_source, "second", named=8, unnamed=2)
    seed(graph_source, "third", named=8, unnamed=2)
    seed(graph_source, "fourth", named=7, unnamed=3)

    outcomes = [observe_in(client, support_kg, s) for s in (FIRST, SECOND, THIRD, FOURTH)]

    assert outcomes[0].drift is None
    assert [marks(o) for o in outcomes[1:]] == [
        [("violation_increase", "Customer.name", True)],
        [("violation_increase", "Customer.name", False)],
        [("violation_increase", "Customer.name", True)],
    ]


def test_a_violation_rate_that_improves_but_stays_above_the_threshold_persists(
    client, support_kg, graph_source
):
    seed(graph_source, "first", named=10)
    seed(graph_source, "second", named=7, unnamed=3)
    seed(graph_source, "third", named=8, unnamed=2)

    outcomes = [observe_in(client, support_kg, s) for s in (FIRST, SECOND, THIRD)]

    assert marks(outcomes[2]) == [("violation_increase", "Customer.name", False)]


def test_a_count_change_is_new_on_every_observation_that_raises_it(
    client, support_kg, graph_source
):
    """Counts compare with the previous Observation, so each finding is a fresh change."""
    seed(graph_source, "first", named=1)
    seed(graph_source, "second", named=2)
    seed(graph_source, "third", named=4)
    thresholds = DriftThresholds(max_count_increase=0.5)

    outcomes = [
        observe_in(client, support_kg, s, thresholds=thresholds) for s in (FIRST, SECOND, THIRD)
    ]

    assert [marks(o) for o in outcomes[1:]] == [
        [("count_increase", "Customer", True)],
        [("count_increase", "Customer", True)],
    ]


PLANT = """
node_types:
  - label: WorkOrder
  - label: Machine
relationship_types:
  - label: ASSIGNED_TO
patterns:
  - [WorkOrder, ASSIGNED_TO, Machine]
"""


def seed_work_orders(graph_source, database, on_a_machine, without, machines=1):
    serving = [graph_source.add_node(["Machine"], {}, database=database) for _ in range(machines)]
    for _ in range(on_a_machine):
        order = graph_source.add_node(["WorkOrder"], {}, database=database)
        graph_source.add_relationship(order, "ASSIGNED_TO", serving[0])
    for _ in range(without):
        graph_source.add_node(["WorkOrder"], {}, database=database)


def test_a_patterns_out_and_in_degree_findings_are_different_findings(client, graph_source):
    """The in-degree Coverage drop is new although the previous Observation had the
    out-degree one on the same pattern, at a lower Coverage."""
    client.create_knowledge_graph("plant", ontology=PLANT)
    seed_work_orders(graph_source, "first", on_a_machine=20, without=0)  # out 100%, in 100%
    seed_work_orders(graph_source, "second", on_a_machine=1, without=19)  # out 5%, in 100%
    seed_work_orders(graph_source, "third", on_a_machine=1, without=19, machines=2)  # in 50%
    coverage = DriftThresholds(max_coverage_drop=0.05)

    outcomes = [observe_in(client, "plant", s, thresholds=coverage) for s in (FIRST, SECOND, THIRD)]

    assert [[(f.kind, f.direction, f.new) for f in o.drift.findings] for o in outcomes[1:]] == [
        [("coverage_drop", "out", True)],
        [("coverage_drop", "out", False), ("coverage_drop", "in", True)],
    ]


PRIORITY = "      - name: priority\n        type: STRING\n        required: true\n"


def promote_a_required_priority(client, kg, support_ontology):
    """A new Ontology Version requiring `Ticket.priority`, which the graph lacks, promoted
    to the Contract Alias."""
    v2 = client.register_ontology(
        kg, support_ontology.replace("        type: DATE\n", "        type: DATE\n" + PRIORITY)
    )
    client.set_alias(kg, client.get_contract_alias(kg), v2.number)


@pytest.mark.parametrize("previous", ["on demand", "run end"])
def test_after_a_promotion_every_finding_is_new(
    client, support_kg, graph_source, support_ontology, previous
):
    """The previous Observation, judged against the old version, raised no event; its
    findings are not recomputed against the new contract, so the gap the Promotion
    introduced is new."""
    seed(graph_source, "first")
    seed(graph_source, "second")
    if previous == "on demand":
        assert observe_in(client, support_kg, FIRST).drift is None
    else:
        client.bind_graph_source(support_kg, FIRST)
        with client.start_run(support_kg):
            pass

    promote_a_required_priority(client, support_kg, support_ontology)
    second = observe_in(client, support_kg, SECOND)

    assert marks(second) == [("vanished", "Ticket.priority", True)]
