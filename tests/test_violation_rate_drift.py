"""Violation Rates and Drift against the Baseline Observation, through the SDK, against the
in-memory fake Graph Source.

A Violation Rate is the share of owner nodes or relationships failing a Conformance check.
Drift compares each one with its value in the Baseline Observation: the first Observation
since the Contract Alias's current Ontology Version became the contract.
"""

import sqlite3
from datetime import date

import pytest

import stetiq
from stetiq import InvalidDriftConfigError
from stetiq.drift import DriftThresholds, thresholds_from_config
from stetiq.graph_source import GraphSourceScope, InMemoryGraphSource

BEFORE, AFTER = GraphSourceScope(database="neo4j"), GraphSourceScope(database="later")


@pytest.fixture
def support_kg(client, support_ontology):
    client.create_knowledge_graph("support", ontology=support_ontology)
    client.bind_graph_source("support", BEFORE)
    return "support"


def seed_customers(graph_source, named, unnamed, database="neo4j"):
    """The support ontology's graph with `named` Customers holding their required `name`
    and `unnamed` ones without it; the first Customer opened one Ticket."""
    customers = [
        graph_source.add_node(["Customer"], {"name": "Ada"}, database=database)
        for _ in range(named)
    ]
    for _ in range(unnamed):
        graph_source.add_node(["Customer"], {}, database=database)
    ticket = graph_source.add_node(["Ticket"], {"opened_at": date(2026, 1, 1)}, database=database)
    graph_source.add_relationship(customers[0], "OPENED", ticket)


def rate_findings(outcome):
    if outcome.drift is None:
        return []
    return [
        (f.kind, f.violation, f.subject, f.baseline_rate, f.observed_rate)
        for f in outcome.drift.findings
        if f.kind == "violation_increase"
    ]


def with_agent(ontology):
    """Another Ontology Version: the support ontology plus an (unobserved) Agent."""
    agent = "  - label: Agent\n    properties:\n      - name: name\n        type: STRING\n"
    return ontology.replace("relationship_types:", agent + "relationship_types:")


def observe_in(client, kg, scope, **kw):
    client.bind_graph_source(kg, scope)
    return client.observe(kg, **kw)


def rates(mismatches):
    return [(m.kind, m.subject, m.rate) for m in mismatches]


# --- Violation Rates in Conformance ------------------------------------------------------


def test_a_required_attribute_left_empty_carries_its_violation_rate(
    client, support_kg, graph_source
):
    client.set_evolution_mode(support_kg, "strict")
    seed_customers(graph_source, named=3, unnamed=1)

    with client.start_run(support_kg) as run:
        pass

    conformance = client.get_run(run.id).conformance
    assert ("required_missing", "Customer.name", 0.25) in rates(conformance.mismatches)


WORK_ORDERS = """
vocabularies:
  - label: Status
    values: [open, closed]
node_types:
  - label: WorkOrder
    properties:
      - {name: status, type: STRING, vocabulary: Status}
"""


@pytest.fixture
def plant(client_factory):
    def create(**kw):
        client = client_factory(**kw)
        client.create_knowledge_graph("plant", ontology=WORK_ORDERS)
        client.bind_graph_source("plant", BEFORE)
        client.set_evolution_mode("plant", "strict")
        return client

    return create


def seed_work_orders(graph_source, *statuses, database="neo4j"):
    for status in statuses:
        graph_source.add_node(["WorkOrder"], {"status": status}, database=database)
    graph_source.add_node(["WorkOrder"], {}, database=database)  # one without a status


def test_a_value_outside_the_vocabulary_carries_its_share_of_the_owner(plant, graph_source):
    client = plant()
    seed_work_orders(graph_source, "open", "open", "on_hold")

    with client.start_run("plant") as run:
        pass

    conformance = client.get_run(run.id).conformance
    assert rates(conformance.mismatches) == [("value_outside_vocabulary", "WorkOrder.status", 0.25)]


def test_a_truncated_value_list_leaves_the_share_unknown(plant, graph_source):
    client = plant(value_cap=1)
    seed_work_orders(graph_source, "on_hold", "on_hold", "open")

    with client.start_run("plant") as run:
        pass

    conformance = client.get_run(run.id).conformance
    assert rates(conformance.mismatches) == [("value_outside_vocabulary", "WorkOrder.status", None)]


# --- Drift on Violation Rates --------------------------------------------------------


def test_a_violation_rate_unchanged_since_the_baseline_is_not_drift(
    client, support_kg, graph_source
):
    seed_customers(graph_source, named=199, unnamed=1)  # 99.5% filled
    seed_customers(graph_source, named=199, unnamed=1, database="later")

    baseline = observe_in(client, support_kg, BEFORE)
    outcome = observe_in(client, support_kg, AFTER)

    assert baseline.drift is None
    assert outcome.drift is None
    assert outcome.observation.baseline_observation_id == baseline.observation.id


def test_a_violation_rate_rising_beyond_the_threshold_since_the_baseline_is_drift(
    client, support_kg, graph_source
):
    seed_customers(graph_source, named=199, unnamed=1)  # 99.5% filled
    seed_customers(graph_source, named=194, unnamed=6, database="later")  # 97%

    observe_in(client, support_kg, BEFORE)
    outcome = observe_in(client, support_kg, AFTER)

    [(kind, violation, subject, baseline_rate, observed_rate)] = rate_findings(outcome)
    assert (kind, violation, subject) == ("violation_increase", "required_missing", "Customer.name")
    assert baseline_rate == pytest.approx(0.005)
    assert observed_rate == pytest.approx(0.03)
    assert outcome.drift.findings[0].subject_kind == "property"
    assert outcome.drift.thresholds.max_violation_increase == 0.01


def test_the_first_observation_is_its_own_baseline_so_no_rate_has_risen_yet(
    client, support_kg, graph_source
):
    seed_customers(graph_source, named=1, unnamed=1)

    outcome = client.observe(support_kg)

    assert outcome.observation.baseline_observation_id == outcome.observation.id
    assert rate_findings(outcome) == []


def test_later_observations_keep_comparing_with_the_same_baseline(client, support_kg, graph_source):
    seed_customers(graph_source, named=199, unnamed=1)
    seed_customers(graph_source, named=197, unnamed=3, database="later")  # +1 point

    baseline = observe_in(client, support_kg, BEFORE)
    observe_in(client, support_kg, AFTER)
    third = observe_in(client, support_kg, AFTER)

    assert third.observation.baseline_observation_id == baseline.observation.id
    assert rate_findings(third) == []  # exactly one point above the baseline: not beyond it


def test_a_promotion_resets_the_baseline_to_the_next_observation(
    client, support_kg, graph_source, support_ontology
):
    seed_customers(graph_source, named=199, unnamed=1)
    seed_customers(graph_source, named=194, unnamed=6, database="later")
    v2 = client.register_ontology(support_kg, with_agent(support_ontology))

    observe_in(client, support_kg, BEFORE)
    client.set_alias(support_kg, "production", v2.number)
    after_promotion = observe_in(client, support_kg, AFTER)
    next_one = observe_in(client, support_kg, AFTER)

    assert after_promotion.observation.baseline_observation_id == after_promotion.observation.id
    assert rate_findings(after_promotion) == []
    assert next_one.observation.baseline_observation_id == after_promotion.observation.id
    assert rate_findings(next_one) == []


def test_switching_the_contract_alias_resets_the_baseline(
    client, support_kg, graph_source, support_ontology
):
    seed_customers(graph_source, named=199, unnamed=1)
    seed_customers(graph_source, named=194, unnamed=6, database="later")
    v2 = client.register_ontology(support_kg, with_agent(support_ontology))
    client.set_alias(support_kg, "staging", v2.number)

    observe_in(client, support_kg, BEFORE)
    client.set_contract_alias(support_kg, "staging")
    outcome = observe_in(client, support_kg, AFTER)

    assert outcome.observation.baseline_observation_id == outcome.observation.id
    assert rate_findings(outcome) == []


def test_designating_the_contract_alias_it_already_is_keeps_the_baseline(
    client, support_kg, graph_source
):
    seed_customers(graph_source, named=199, unnamed=1)
    seed_customers(graph_source, named=194, unnamed=6, database="later")

    baseline = observe_in(client, support_kg, BEFORE)
    client.set_contract_alias(support_kg, "production")
    outcome = observe_in(client, support_kg, AFTER)

    assert outcome.observation.baseline_observation_id == baseline.observation.id
    assert len(rate_findings(outcome)) == 1


def test_an_observation_ending_a_run_can_be_the_baseline(client, support_kg, graph_source):
    seed_customers(graph_source, named=199, unnamed=1)
    seed_customers(graph_source, named=194, unnamed=6, database="later")
    with client.start_run(support_kg) as run:
        pass

    outcome = observe_in(client, support_kg, AFTER)

    assert outcome.observation.baseline_observation_id == client.get_run(run.id).observation_id
    assert len(rate_findings(outcome)) == 1


def test_a_null_max_violation_increase_turns_the_check_off(client, support_kg, graph_source):
    off = DriftThresholds(max_violation_increase=None)
    seed_customers(graph_source, named=199, unnamed=1)
    seed_customers(graph_source, named=100, unnamed=100, database="later")

    observe_in(client, support_kg, BEFORE, thresholds=off)
    outcome = observe_in(client, support_kg, AFTER, thresholds=off)

    assert outcome.drift is None
    assert outcome.observation.not_comparable == ()


def test_a_configured_max_violation_increase_is_used(client, support_kg, graph_source):
    seed_customers(graph_source, named=199, unnamed=1)
    seed_customers(graph_source, named=194, unnamed=6, database="later")
    loose = DriftThresholds(max_violation_increase=0.05)

    observe_in(client, support_kg, BEFORE, thresholds=loose)
    outcome = observe_in(client, support_kg, AFTER, thresholds=loose)

    assert outcome.drift is None


def test_a_required_attribute_the_baseline_did_not_observe_is_not_comparable(
    client, support_kg, graph_source
):
    graph_source.add_node(["Customer"], {})  # the baseline saw Customers, none with a name
    seed_customers(graph_source, named=1, unnamed=1, database="later")

    observe_in(client, support_kg, BEFORE)
    outcome = observe_in(client, support_kg, AFTER)

    assert rate_findings(outcome) == []
    assert [
        (str(e.check), e.violation, e.subject, e.subject_kind)
        for e in outcome.observation.not_comparable
    ] == [("violation_increase", "required_missing", "Customer.name", "property")]
    assert client.get_observation(outcome.observation.id) == outcome.observation


def test_a_truncated_value_list_is_not_comparable_and_never_a_rate_finding(plant, graph_source):
    client = plant(value_cap=1)
    seed_work_orders(graph_source, "open", "open")
    seed_work_orders(graph_source, "on_hold", "on_hold", "on_hold", "open", database="later")

    observe_in(client, "plant", BEFORE)
    outcome = observe_in(client, "plant", AFTER)

    assert [(str(f.kind), f.value, f.count, f.share) for f in outcome.drift.findings] == [
        ("undeclared_value", "on_hold", 3, None)
    ]
    assert [(str(e.check), e.subject) for e in outcome.observation.not_comparable] == [
        ("undeclared_value", "WorkOrder.status")
    ]
    assert client.list_observations("plant")[-1] == outcome.observation


def test_an_undeclared_value_carries_its_count_and_share(plant, graph_source):
    client = plant()
    seed_work_orders(graph_source, "open", "on_hold", "on_hold")

    outcome = client.observe("plant")

    assert [(str(f.kind), f.value, f.count, f.share) for f in outcome.drift.findings] == [
        ("undeclared_value", "on_hold", 2, 0.5)
    ]
    assert client.list_drift_events("plant") == [outcome.drift]


# --- `max_violation_increase` in stetiq.yaml: missing means 0.01, null means off -----------


def test_a_missing_max_violation_increase_in_the_repo_config_means_one_point():
    assert thresholds_from_config({}).max_violation_increase == 0.01
    assert thresholds_from_config({"drift": {}}).max_violation_increase == 0.01
    assert thresholds_from_config({"drift": {"max_count_drop": 0.1}}) == DriftThresholds(
        max_count_drop=0.1, max_violation_increase=0.01
    )


def test_a_null_max_violation_increase_in_the_repo_config_turns_the_check_off():
    config = {"drift": {"max_violation_increase": None}}

    assert thresholds_from_config(config).max_violation_increase is None


@pytest.mark.parametrize(
    "section",
    [{"max_violation_increase": -0.01}, {"max_violation_increase": True}, {"max_violation": 0.1}],
)
def test_a_malformed_or_unknown_drift_key_is_rejected(section):
    with pytest.raises(InvalidDriftConfigError):
        thresholds_from_config({"drift": section})


# --- Stores from before Baseline Observations -------------------------------------------


def test_a_database_from_before_baselines_gains_the_columns_on_startup(tmp_path, support_ontology):
    url = f"sqlite:///{tmp_path / 'stetiq.db'}"
    graph = InMemoryGraphSource()
    seed_customers(graph, named=199, unnamed=1)
    seed_customers(graph, named=194, unnamed=6, database="later")
    first = stetiq.Client(url, graph_source=graph)
    first.create_knowledge_graph("support", ontology=support_ontology)
    first.set_alias("support", "staging", 1)
    first.set_contract_alias("support", "staging")
    first.bind_graph_source("support", BEFORE)
    baseline = first.observe("support")
    with sqlite3.connect(tmp_path / "stetiq.db") as db:
        for table, column in (
            ("observations", "baseline_observation_id"),
            ("observations", "not_comparable_json"),
            ("contract_aliases", "switched_at"),
        ):
            db.execute(f"ALTER TABLE {table} DROP COLUMN {column}")

    client = stetiq.Client(url, graph_source=graph)
    outcome = observe_in(client, "support", AFTER)

    # The switch's time is lost, so the baseline is the first since `staging` last moved.
    assert outcome.observation.baseline_observation_id == baseline.observation.id
    assert len(rate_findings(outcome)) == 1
    assert client.get_observation(baseline.observation.id).baseline_observation_id is None
