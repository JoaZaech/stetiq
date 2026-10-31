"""Gates as code: rules from the repo config file, evaluated through the SDK against
results stored on the server, recorded there, and reflected in the Promotion audit log."""

from datetime import date
from pathlib import Path

import pytest

import stetiq
from stetiq.graph_source import GraphSourceScope

NO_BREAKING = """
gates:
  - name: no-breaking-changes
    check: ontology_diff
    max_classification: deprecating
"""

# Version 2: adds Agent (additive). Version 3: removes OPENED (breaking).
WITH_AGENT = """
node_types:
  - label: Customer
    properties:
      - {name: name, type: STRING, required: true}
  - label: Ticket
    description: A support request
    properties:
      - {name: opened_at, type: DATE}
  - label: Agent
relationship_types:
  - label: OPENED
patterns:
  - [Customer, OPENED, Ticket]
"""

WITHOUT_OPENED = """
node_types:
  - label: Customer
    properties:
      - {name: name, type: STRING, required: true}
  - label: Ticket
    description: A support request
    properties:
      - {name: opened_at, type: DATE}
"""


@pytest.fixture
def support_kg(client, support_ontology):
    client.create_knowledge_graph("support", ontology=support_ontology)
    client.register_ontology("support", WITH_AGENT)  # v2
    client.register_ontology("support", WITHOUT_OPENED)  # v3
    return "support"


def test_a_version_without_breaking_changes_against_the_contract_passes_a_diff_gate(
    client, support_kg
):
    result = client.evaluate_gates(support_kg, NO_BREAKING, version=2)

    assert result.passed
    assert [(o.gate.name, o.passed) for o in result.outcomes] == [("no-breaking-changes", True)]


def test_a_breaking_version_fails_the_diff_gate_naming_the_breaking_changes(client, support_kg):
    result = client.evaluate_gates(support_kg, NO_BREAKING, version=3)

    assert not result.passed
    [outcome] = result.failed
    assert outcome.gate.name == "no-breaking-changes"
    assert any("OPENED" in reason and "breaking" in reason for reason in outcome.reasons)


def test_a_cosmetic_only_diff_gate_lets_description_changes_through_and_nothing_else(
    client, support_kg
):
    only_cosmetic = NO_BREAKING.replace(
        "max_classification: deprecating", "max_classification: cosmetic"
    )
    redescribed = client.register_ontology(  # v4: v1 with Ticket described differently
        support_kg, WITH_AGENT.replace("A support request", "A customer's request")
    )
    client.set_alias(support_kg, "production", 2)

    assert client.evaluate_gates(support_kg, only_cosmetic, version=redescribed.number).passed
    assert client.evaluate_gates(support_kg, NO_BREAKING, version=redescribed.number).passed
    [outcome] = client.evaluate_gates(support_kg, only_cosmetic, version=3).failed
    assert any("OPENED" in reason and "breaking" in reason for reason in outcome.reasons)


def test_every_gate_evaluation_is_recorded_on_the_server_with_the_gate_definition_used(
    client_factory, support_ontology
):
    client = client_factory()
    client.create_knowledge_graph("support", ontology=support_ontology)
    client.register_ontology("support", WITHOUT_OPENED)  # v2, breaking
    client.evaluate_gates("support", NO_BREAKING, version=2)

    [recorded] = client_factory().list_gate_results("support")

    assert (recorded.subject_kind, recorded.subject_id, recorded.ontology_version) == (
        "ontology_version",
        "2",
        2,
    )
    assert not recorded.passed
    assert [g.to_dict() for g in recorded.gates] == [
        {
            "name": "no-breaking-changes",
            "check": "ontology_diff",
            "max_classification": "deprecating",
        }
    ]
    assert any("OPENED" in r for r in recorded.failed[0].reasons)


def test_the_promotion_audit_log_records_the_target_versions_latest_gate_result(client, support_kg):
    client.evaluate_gates(support_kg, NO_BREAKING, version=3)  # fails
    client.evaluate_gates(support_kg, NO_BREAKING, version=2)  # passes
    client.set_alias(support_kg, "staging", 3)
    client.set_alias(support_kg, "production", 2)
    client.set_alias(support_kg, "canary", 1)  # never gated

    log = {(p.alias, p.to_version): p.gate_result for p in client.list_promotions(support_kg)}

    assert log[("staging", 3)] == "failed"
    assert log[("production", 2)] == "passed"
    assert log[("canary", 1)] is None


def test_a_later_gate_result_replaces_the_earlier_one_in_the_audit_log(client, support_kg):
    client.evaluate_gates(support_kg, NO_BREAKING, version=3)  # fails
    lenient = NO_BREAKING.replace("max_classification: deprecating", "max_classification: breaking")
    client.evaluate_gates(support_kg, lenient, version=3)  # passes

    client.set_alias(support_kg, "staging", 3)

    assert client.list_promotions(support_kg)[-1].gate_result == "passed"


# --- Evaluator results ----------------------------------------------------------------

NO_ISOLATED = """
gates:
  - name: no-isolated-types
    check: metric
    evaluator: isolated_node_types
    metric: isolated_node_types
    max: 0
"""


def test_a_metric_gate_checks_the_versions_latest_evaluator_result(client, support_kg):
    connected = client.evaluate_gates(support_kg, NO_ISOLATED, version=1)
    isolated = client.evaluate_gates(support_kg, NO_ISOLATED, version=2)  # Agent is isolated

    assert connected.passed
    assert not isolated.passed
    assert "isolated_node_types.isolated_node_types = 1 > max 0" in isolated.failed[0].reasons[0]


class CompetencyQuestions(stetiq.OntologyVersionEvaluator):
    """Stands in for a Use Case Evaluator: Tickets must be reachable from Customers."""

    name = "competency_questions"

    def evaluate(self, version):
        answerable = any(r.label == "OPENED" for r in version.ontology.relationship_types)
        return stetiq.Evaluation(
            metrics={"unanswerable": 0 if answerable else 1},
            details=()
            if answerable
            else (stetiq.Detail("cq-1", "Which tickets did Ada open?", "unanswerable"),),
        )


ALL_CQS_ANSWERABLE = """
gates:
  - name: all-cqs-answerable
    check: metric
    evaluator: competency_questions
    metric: unanswerable
    max: 0
"""


def test_a_metric_gate_over_a_custom_evaluator_lists_its_details_as_reasons(
    client_factory, support_ontology
):
    client = client_factory()
    client.register_evaluator(CompetencyQuestions())
    client.create_knowledge_graph("support", ontology=support_ontology)
    client.register_ontology("support", WITHOUT_OPENED)  # v2

    passing = client_factory().evaluate_gates("support", ALL_CQS_ANSWERABLE, version=1)
    failing = client_factory().evaluate_gates("support", ALL_CQS_ANSWERABLE, version=2)

    assert passing.passed
    assert not failing.passed
    assert any("cq-1" in r and "Which tickets" in r for r in failing.failed[0].reasons)


def test_a_metric_gate_fails_when_the_evaluator_has_no_result(client, support_kg):
    result = client.evaluate_gates(support_kg, ALL_CQS_ANSWERABLE, version=1)

    assert not result.passed
    assert "No result of Evaluator 'competency_questions'" in result.failed[0].reasons[0]


def test_a_metric_gate_supports_a_lower_bound(client, support_kg):
    gates = """
gates:
  - check: metric
    evaluator: hierarchy
    metric: root_node_types
    min: 3
"""
    result = client.evaluate_gates(support_kg, gates, version=2)  # 3 root node types

    assert result.passed
    assert result.outcomes[0].gate.name == "metric"


# --- Runs: Conformance and statistics -------------------------------------------------

CONFORMANCE = """
gates:
  - name: conformance
    check: conformance
    min_score: 0.95
"""


@pytest.fixture
def bound_kg(client, support_ontology):
    client.create_knowledge_graph("support", ontology=support_ontology)
    client.bind_graph_source("support", GraphSourceScope(database="neo4j"))
    return "support"


def seed_conforming_graph(graph_source, customers=1):
    for i in range(customers):
        customer = graph_source.add_node(["Customer"], {"name": f"c{i}"})
        ticket = graph_source.add_node(["Ticket"], {"opened_at": date(2026, 1, 1)})
        graph_source.add_relationship(customer, "OPENED", ticket)


def run_once(client, kg, **kw):
    with client.start_run(kg, **kw) as run:
        pass
    return client.get_run(run.id)


def test_a_conforming_run_passes_a_conformance_gate(client, bound_kg, graph_source):
    seed_conforming_graph(graph_source)
    run = run_once(client, bound_kg)

    result = client.evaluate_gates(bound_kg, CONFORMANCE, run=run.id)

    assert result.passed
    assert (result.subject_kind, result.subject_id, result.ontology_version) == (
        "construction_run",
        run.id,
        1,
    )


def test_a_run_below_the_conformance_threshold_fails_with_its_score_and_mismatches(
    client, bound_kg, graph_source
):
    graph_source.add_node(["Customer"], {"name": "Ada"})  # no Ticket, no OPENED
    run = run_once(client, bound_kg)

    result = client.evaluate_gates(bound_kg, CONFORMANCE, run=run.id)

    assert not result.passed
    reasons = result.failed[0].reasons
    assert "0.95" in reasons[0] and f"{run.conformance.score:.2f}" in reasons[0]
    assert any("Ticket" in r and "absent" in r for r in reasons[1:])


def test_a_candidate_is_gated_with_the_conformance_of_the_run_that_gave_rise_to_it(
    client, bound_kg, graph_source
):
    seed_conforming_graph(graph_source)
    graph_source.add_node(["Agent"], {"name": "Grace"})  # new Concept -> Candidate v2
    run = run_once(client, bound_kg)
    assert run.candidate_version == 2

    by_version = client.evaluate_gates(bound_kg, CONFORMANCE, version=2)
    by_run = client.evaluate_gates(bound_kg, CONFORMANCE, run=run.id)

    assert by_run.ontology_version == 2
    assert not by_version.passed and not by_run.passed
    assert by_version.failed[0].reasons[0] == by_run.failed[0].reasons[0]


def test_a_version_no_run_has_produced_or_consumed_fails_a_conformance_gate(client, bound_kg):
    result = client.evaluate_gates(bound_kg, CONFORMANCE, version=1)

    assert not result.passed
    assert "No Conformance" in result.failed[0].reasons[0]


COUNT_DROP = """
gates:
  - name: no-type-count-drops
    check: count_drop
    max_drop: 0.10
"""


def seed_in_namespace(graph_source, namespace, customers, tickets_per_customer=1):
    for i in range(customers):
        customer = graph_source.add_node(["Customer"], {"name": f"c{i}", "namespace": namespace})
        for _ in range(tickets_per_customer):
            ticket = graph_source.add_node(
                ["Ticket"], {"opened_at": date(2026, 1, 1), "namespace": namespace}
            )
            graph_source.add_relationship(customer, "OPENED", ticket)


def run_in_namespace(client, kg, namespace):
    client.bind_graph_source(kg, GraphSourceScope(database="neo4j", namespace=namespace))
    return run_once(client, kg)


def test_a_run_whose_type_counts_drop_more_than_allowed_fails_naming_the_types(
    client, bound_kg, graph_source
):
    seed_in_namespace(graph_source, "before", customers=10)
    seed_in_namespace(graph_source, "after", customers=8)
    run_in_namespace(client, bound_kg, "before")
    run = run_in_namespace(client, bound_kg, "after")

    result = client.evaluate_gates(bound_kg, COUNT_DROP, run=run.id)

    assert not result.passed
    reasons = result.failed[0].reasons
    assert "node type Customer: 10 -> 8 (-20.0%)" in reasons
    assert "relationship type OPENED: 10 -> 8 (-20.0%)" in reasons


def test_counts_within_the_allowed_drop_pass(client, bound_kg, graph_source):
    seed_in_namespace(graph_source, "before", customers=10)
    seed_in_namespace(graph_source, "after", customers=11)
    run_in_namespace(client, bound_kg, "before")
    run = run_in_namespace(client, bound_kg, "after")

    assert client.evaluate_gates(bound_kg, COUNT_DROP, run=run.id).passed


def test_a_type_that_disappears_counts_as_a_full_drop(client, bound_kg, graph_source):
    seed_in_namespace(graph_source, "before", customers=2)
    graph_source.add_node(["Customer"], {"name": "lonely", "namespace": "after"})
    run_in_namespace(client, bound_kg, "before")
    run = run_in_namespace(client, bound_kg, "after")

    result = client.evaluate_gates(bound_kg, COUNT_DROP, run=run.id)

    assert "node type Ticket: 2 -> 0 (-100.0%)" in result.failed[0].reasons


def test_the_first_observation_has_no_baseline_so_nothing_can_have_dropped(
    client, bound_kg, graph_source
):
    seed_conforming_graph(graph_source)
    run = run_once(client, bound_kg)

    result = client.evaluate_gates(bound_kg, COUNT_DROP, run=run.id)

    assert result.passed
    assert "No earlier Observation" in result.outcomes[0].reasons[0]


# --- The repo config file ---------------------------------------------------------------


def test_gates_are_read_from_the_repo_config_file_ignoring_other_sections(
    client, support_kg, tmp_path
):
    config = tmp_path / "stetiq.yaml"
    config.write_text(
        "knowledge_graph: support\n"
        "entry_point: {command: ./build.sh}\n"
        "drift: {max_count_drop: 0.2}\n" + NO_BREAKING + NO_ISOLATED.replace("gates:\n", "")
    )

    result = client.evaluate_gates(support_kg, Path(config), version=2)

    assert [(o.gate.name, o.passed) for o in result.outcomes] == [
        ("no-breaking-changes", True),
        ("no-isolated-types", False),  # v2's Agent is isolated
    ]


def test_without_a_version_the_latest_version_is_gated(client, support_kg):
    assert client.evaluate_gates(support_kg, NO_BREAKING).ontology_version == 3


@pytest.mark.parametrize(
    ("config", "message"),
    [
        ("gates: [{check: nope}]", "unknown check 'nope'"),
        ("gates: [{check: conformance}]", "missing 'min_score'"),
        ("gates: [{check: conformance, min_score: 2}]", "between 0 and 1"),
        ("gates: [{check: conformance, min_score: 0.9, typo: 1}]", "unknown key(s) typo"),
        (
            "gates: [{check: ontology_diff, max_classification: awful}]",
            "cosmetic, additive, deprecating or breaking",
        ),
        ("gates: [{check: metric, evaluator: x, metric: y}]", "'min' and/or 'max'"),
        (
            "gates: [{check: count_drop, max_drop: 0.1}, {check: count_drop, max_drop: 0.2}]",
            "Duplicate Gate names",
        ),
        ("gates: {check: conformance}", "must be a list"),
    ],
)
def test_malformed_gates_are_rejected_naming_the_problem(client, support_kg, config, message):
    with pytest.raises(stetiq.GateConfigError) as raised:
        client.evaluate_gates(support_kg, config)

    assert message in str(raised.value)
    assert client.list_gate_results(support_kg) == []
