"""On-demand Observation and Drift, through the SDK, against the in-memory fake Graph Source.

Drift compares each on-demand Observation with the Contract Alias's Ontology Version
(structure) and with the previous Observation (statistics, beyond configured thresholds).
To make the live graph change between two Observations, tests seed two databases and
rebind the Knowledge Graph's scope from one to the other.
"""

from datetime import date

import pytest

from stetiq import GraphSourceNotBoundError, GraphSourceUnavailableError, InvalidDriftConfigError
from stetiq.drift import DriftThresholds, thresholds_from_config
from stetiq.graph_source import GraphSourceScope

BEFORE, AFTER = GraphSourceScope(database="neo4j"), GraphSourceScope(database="later")


@pytest.fixture
def support_kg(client, support_ontology):
    client.create_knowledge_graph("support", ontology=support_ontology)
    client.bind_graph_source("support", BEFORE)
    return "support"


def seed_conforming_graph(graph_source, tickets=1, database="neo4j"):
    """Exactly the support ontology: Customer(name)-[OPENED]->Ticket(opened_at)."""
    ada = graph_source.add_node(["Customer"], {"name": "Ada"}, database=database)
    for _ in range(tickets):
        ticket = graph_source.add_node(
            ["Ticket"], {"opened_at": date(2026, 1, 1)}, database=database
        )
        graph_source.add_relationship(ada, "OPENED", ticket)
    return ada


def kinds_and_subjects(findings):
    return [(str(f.kind), f.subject) for f in findings]


def statistical(findings):
    return [(str(f.kind), f.subject, f.previous_count, f.observed_count) for f in findings]


def test_observe_captures_the_observed_schema_outside_a_run(client, support_kg, graph_source):
    seed_conforming_graph(graph_source, tickets=2)

    outcome = client.observe(support_kg)

    assert outcome.observation.run_id is None
    assert outcome.observation.schema.node_type("Ticket").count == 2
    assert [o.id for o in client.list_observations(support_kg)] == [outcome.observation.id]
    assert client.list_runs(support_kg) == []


def test_an_observation_matching_the_contract_raises_no_drift(client, support_kg, graph_source):
    seed_conforming_graph(graph_source)

    outcome = client.observe(support_kg)

    assert outcome.drift is None
    assert not outcome.drifted
    assert client.list_drift_events(support_kg) == []


def test_undeclared_concepts_are_structural_drift(client, support_kg, graph_source):
    ada = seed_conforming_graph(graph_source)
    grace = graph_source.add_node(["Agent"], {"name": "Grace"})
    graph_source.add_relationship(grace, "ASSIGNED", ada)

    outcome = client.observe(support_kg)

    assert outcome.drifted
    assert kinds_and_subjects(outcome.drift.findings) == [
        ("undeclared", "Agent"),
        ("undeclared", "Agent.name"),
        ("undeclared", "ASSIGNED"),
    ]
    assert outcome.drift.observation_id == outcome.observation.id
    assert outcome.drift.contract_alias == "production"
    assert outcome.drift.ontology_version == 1


def test_vanished_declared_concepts_are_structural_drift(client, support_kg, graph_source):
    graph_source.add_node(["Customer"], {"name": "Ada"})

    outcome = client.observe(support_kg)

    assert kinds_and_subjects(outcome.drift.structural) == [
        ("vanished", "Ticket"),
        ("vanished", "Ticket.opened_at"),
        ("vanished", "OPENED"),
    ]
    assert outcome.drift.statistical == ()


AGENT = "  - label: Agent\n    properties:\n      - name: name\n        type: STRING\n"


def test_drift_is_measured_against_the_contract_alias_version(
    client, support_kg, graph_source, support_ontology
):
    seed_conforming_graph(graph_source)
    graph_source.add_node(["Agent"], {"name": "Grace"})
    v2 = client.register_ontology(
        support_kg, support_ontology.replace("relationship_types:", AGENT + "relationship_types:")
    )

    before = client.observe(support_kg)
    client.set_alias(support_kg, "staging", v2.number)
    client.set_contract_alias(support_kg, "staging")
    after = client.observe(support_kg)

    assert before.drifted
    assert not after.drifted


def test_drift_never_creates_an_ontology_version(client, support_kg, graph_source):
    client.set_evolution_mode(support_kg, "evolving")
    seed_conforming_graph(graph_source)
    graph_source.add_node(["Agent"], {"name": "Grace"})

    outcome = client.observe(support_kg)

    assert outcome.drifted
    assert [v.number for v in client.list_ontology_versions(support_kg)] == [1]
    assert [(a.name, a.version) for a in client.list_aliases(support_kg)] == [("production", 1)]


def test_a_count_dropping_beyond_the_threshold_since_the_previous_observation_is_statistical_drift(
    client, support_kg, graph_source
):
    thresholds = DriftThresholds(max_count_drop=0.1)
    seed_conforming_graph(graph_source, tickets=10)
    seed_conforming_graph(graph_source, tickets=8, database="later")

    first = client.observe(support_kg, thresholds=thresholds)
    client.bind_graph_source(support_kg, AFTER)
    second = client.observe(support_kg, thresholds=thresholds)

    assert not first.drifted
    assert statistical(second.drift.findings) == [
        ("count_drop", "Ticket", 10, 8),
        ("count_drop", "OPENED", 10, 8),
    ]
    assert second.drift.structural == ()
    assert second.drift.previous_observation_id == first.observation.id
    assert second.drift.thresholds == thresholds


def test_a_count_change_within_the_threshold_is_not_drift(client, support_kg, graph_source):
    thresholds = DriftThresholds(max_count_drop=0.2, max_count_increase=0.2)
    seed_conforming_graph(graph_source, tickets=10)
    seed_conforming_graph(graph_source, tickets=8, database="later")

    client.observe(support_kg, thresholds=thresholds)
    client.bind_graph_source(support_kg, AFTER)
    second = client.observe(support_kg, thresholds=thresholds)

    assert not second.drifted  # exactly -20%: at the threshold, not beyond it


def test_a_count_rising_beyond_the_increase_threshold_is_statistical_drift(
    client, support_kg, graph_source
):
    thresholds = DriftThresholds(max_count_increase=0.5)
    seed_conforming_graph(graph_source, tickets=2)
    seed_conforming_graph(graph_source, tickets=4, database="later")

    client.observe(support_kg, thresholds=thresholds)
    client.bind_graph_source(support_kg, AFTER)
    second = client.observe(support_kg, thresholds=thresholds)

    assert statistical(second.drift.findings) == [
        ("count_increase", "Ticket", 2, 4),
        ("count_increase", "OPENED", 2, 4),
    ]


def test_without_thresholds_count_changes_are_not_drift(client, support_kg, graph_source):
    seed_conforming_graph(graph_source, tickets=10)
    seed_conforming_graph(graph_source, tickets=1, database="later")

    client.observe(support_kg)
    client.bind_graph_source(support_kg, AFTER)

    assert not client.observe(support_kg).drifted


def test_statistics_compare_with_the_previous_observation_even_one_ending_a_run(
    client, support_kg, graph_source
):
    seed_conforming_graph(graph_source, tickets=10)
    seed_conforming_graph(graph_source, tickets=5, database="later")
    with client.start_run(support_kg) as run:
        pass

    client.bind_graph_source(support_kg, AFTER)
    outcome = client.observe(support_kg, thresholds=DriftThresholds(max_count_drop=0.1))

    ended = client.get_run(run.id)
    assert outcome.drift.previous_observation_id == ended.observation_id
    assert statistical(outcome.drift.findings)[0] == ("count_drop", "Ticket", 10, 5)


def test_drift_events_are_listed_per_knowledge_graph_oldest_first(
    client, support_kg, graph_source, support_ontology
):
    client.create_knowledge_graph("other", ontology=support_ontology)
    client.bind_graph_source("other", BEFORE)
    graph_source.add_node(["Customer"], {"name": "Ada"})

    first = client.observe(support_kg)
    second = client.observe(support_kg)

    assert [e.id for e in client.list_drift_events(support_kg)] == [first.drift.id, second.drift.id]
    assert client.list_drift_events(support_kg)[0] == first.drift
    assert client.list_drift_events("other") == []


def test_observe_needs_a_bound_graph_source(client, support_ontology):
    client.create_knowledge_graph("unbound", ontology=support_ontology)

    with pytest.raises(GraphSourceNotBoundError):
        client.observe("unbound")
    assert client.list_observations("unbound") == []


def test_observe_needs_a_graph_source_adapter(client_factory, support_ontology):
    client = client_factory(graph_source=None)
    client.create_knowledge_graph("support", ontology=support_ontology)
    client.bind_graph_source("support", BEFORE)

    with pytest.raises(GraphSourceUnavailableError):
        client.observe("support")


# --- Thresholds from the repo config (`drift:` section of stetiq.yaml) ------------------


def test_thresholds_come_from_the_drift_section_of_the_repo_config():
    config = {"knowledge_graph": "support", "gates": [], "drift": {"max_count_drop": 0.1}}

    assert thresholds_from_config(config) == DriftThresholds(max_count_drop=0.1)
    assert thresholds_from_config({}) == DriftThresholds()


@pytest.mark.parametrize(
    "section",
    [
        {"max_count_drop": -0.1},
        {"max_count_drop": "10%"},
        {"max_count_dorp": 0.1},
        ["max_count_drop"],
    ],
)
def test_a_malformed_drift_section_is_rejected(section):
    with pytest.raises(InvalidDriftConfigError):
        thresholds_from_config({"drift": section})
