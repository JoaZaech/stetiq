"""Run-level evaluation: Conformance and Observed Schema statistics as evaluation
results on a Construction Run, and executed Competency Questions, through the SDK
against the in-memory fake Graph Source."""

from datetime import date

import pytest

import stetiq
from stetiq.graph_source import GraphSourceScope


@pytest.fixture
def support_kg(client, support_ontology):
    client.create_knowledge_graph("support", ontology=support_ontology)
    client.bind_graph_source("support", GraphSourceScope(database="neo4j"))
    return "support"


def seed_support_graph(graph_source):
    """Two Customers (one without a name), one Ticket, one OPENED."""
    ada = graph_source.add_node(["Customer"], {"name": "Ada"})
    graph_source.add_node(["Customer"], {})
    ticket = graph_source.add_node(["Ticket"], {"opened_at": date(2026, 1, 1)})
    graph_source.add_relationship(ada, "OPENED", ticket)


def run_once(client, kg="support"):
    with client.start_run(kg, ontology_version=1) as run:
        pass
    return client.get_run(run.id)


def result(results, evaluator):
    [found] = [r for r in results if r.evaluator == evaluator]
    return found


def test_conformance_appears_as_an_evaluation_result_on_the_run(client, support_kg, graph_source):
    seed_support_graph(graph_source)

    run = run_once(client)

    conformance = result(client.get_run_evaluation_results(run.id), "conformance")
    assert conformance.subject_kind == "construction_run"
    assert conformance.subject_id == run.id
    # 6 elements, all present; Customer.name is required but only half filled.
    assert conformance.metrics == {
        "score": 5 / 6,
        "mismatches": 1,
        "declared_absent": 0,
        "undeclared": 0,
        "pattern_mismatches": 0,
        "property_mismatches": 1,
    }
    [detail] = conformance.details
    assert detail.item == "Customer.name"
    assert detail.metric == "property_mismatches"
    assert detail.data == {"subject_kind": "property", "kind": "required_missing"}


def test_observed_schema_statistics_appear_as_an_evaluation_result_on_the_run(
    client, support_kg, graph_source
):
    seed_support_graph(graph_source)

    run = run_once(client)

    stats = result(client.get_run_evaluation_results(run.id), "observed_schema")
    assert stats.metrics == {
        "node_types": 2,
        "relationship_types": 1,
        "patterns": 1,
        "nodes": 3,
        "relationships": 1,
        "properties": 2,
        "mean_fill_rate": 0.75,  # Customer.name 1/2, Ticket.opened_at 1/1
    }
    by_item = {d.item: d for d in stats.details}
    assert by_item["Customer"].data == {"count": 2, "fill_rates": {"name": 0.5}}
    assert by_item["OPENED"].data == {"count": 1, "fill_rates": {}}
    assert by_item["(Customer)-[OPENED]->(Ticket)"].data == {
        "count": 1,
        "out_degree": {"min": 0, "max": 1, "mean": 0.5},
        "in_degree": {"min": 1, "max": 1, "mean": 1.0},
    }


WHO_OPENED = "MATCH (c:Customer)-[:OPENED]->(t:Ticket) RETURN c.name AS name"
OPEN_COUNT = "MATCH (t:Ticket) RETURN count(t) AS tickets"
NO_AGENTS = "MATCH (a:Agent) RETURN a.name AS name"


def statuses(execution):
    return {d.item: d.data["status"] for d in execution.details}


def test_competency_questions_with_a_query_pass_when_their_result_is_non_empty(
    client, support_kg, graph_source
):
    seed_support_graph(graph_source)
    graph_source.add_query_result(WHO_OPENED, [{"name": "Ada"}])
    graph_source.add_query_result(NO_AGENTS, [])
    use_case = client.register_use_case(
        support_kg,
        [
            stetiq.CompetencyQuestion("who-opened", "Who opened tickets?", query=WHO_OPENED),
            stetiq.CompetencyQuestion("agents", "Which agents exist?", query=NO_AGENTS),
            stetiq.CompetencyQuestion("why", "Why do customers churn?"),  # no query
        ],
    )

    run = run_once(client)

    execution = result(client.get_run_evaluation_results(run.id), "competency_question_execution")
    assert execution.use_case_version == use_case.number
    assert execution.metrics == {
        "questions": 2,
        "passed_questions": 1,
        "failed_questions": 1,
        "skipped_questions": 1,
        "pass_ratio": 0.5,
    }
    assert statuses(execution) == {"agents": "failed", "who-opened": "passed"}
    by_item = {d.item: d for d in execution.details}
    assert by_item["who-opened"].metric == "passed_questions"
    assert by_item["agents"].metric == "failed_questions"
    assert by_item["agents"].data["rows"] == 0


@pytest.mark.parametrize(
    ("rows", "expected_answer", "status"),
    [
        ([{"tickets": 1}], 1, "passed"),  # a scalar: one single-column row
        ([{"tickets": 2}], 1, "failed"),
        ([{"tickets": 1}, {"tickets": 1}], 1, "failed"),
        ([{"ok": True}], 1, "failed"),  # JSON true is not 1
        ([{"name": "Ada"}, {"name": "Bob"}], ["Bob", "Ada"], "passed"),  # values, any order
        ([{"name": "Ada"}], ["Ada", "Bob"], "failed"),
        ([{"name": "Ada", "n": 1}], {"name": "Ada", "n": 1}, "passed"),  # a mapping: one row
        ([{"name": "Ada", "n": 2}], {"name": "Ada", "n": 1}, "failed"),
        (
            [{"name": "Bob", "n": 1}, {"name": "Ada", "n": 2}],
            [{"name": "Ada", "n": 2}, {"name": "Bob", "n": 1}],
            "passed",
        ),  # rows, any order
        ([], [], "passed"),  # an expected empty answer
    ],
)
def test_a_competency_question_with_an_expected_answer_passes_only_when_the_result_matches_it(
    client, support_kg, graph_source, rows, expected_answer, status
):
    seed_support_graph(graph_source)
    graph_source.add_query_result(OPEN_COUNT, rows)
    client.register_use_case(
        support_kg,
        [
            stetiq.CompetencyQuestion(
                "q", "How many tickets?", query=OPEN_COUNT, expected_answer=expected_answer
            )
        ],
    )

    run = run_once(client)

    execution = result(client.get_run_evaluation_results(run.id), "competency_question_execution")
    assert statuses(execution) == {"q": status}
    assert execution.details[0].data["check"] == "expected_answer"


class ExplodingGraphSource:
    """Observes like the fake, but every read fails with a message quoting instance data."""

    def __init__(self, inner):
        self.inner = inner

    def observe(self, scope):
        return self.inner.observe(scope)

    def execute_read(self, scope, query, parameters=None):
        raise RuntimeError("Cannot coerce 'Ada Lovelace-7731' to INTEGER")


def stored_text(client, run_id):
    return repr(
        [
            client.get_run(run_id),
            client.list_observations("support"),
            client.get_run_evaluation_results(run_id),
        ]
    )


def test_returned_instance_data_is_never_persisted(client_factory, support_kg, graph_source):
    secret = "Ada Lovelace-7731"
    client = client_factory()
    seed_support_graph(graph_source)
    graph_source.add_query_result(WHO_OPENED, [{"name": secret}])
    client.register_use_case(
        "support",
        [
            stetiq.CompetencyQuestion("q1", "Who opened tickets?", query=WHO_OPENED),
            stetiq.CompetencyQuestion(
                "q2", "Is Grace a customer?", query=WHO_OPENED, expected_answer="Grace"
            ),
        ],
    )

    run = run_once(client)

    results = client.get_run_evaluation_results(run.id)
    assert statuses(result(results, "competency_question_execution")) == {
        "q1": "passed",
        "q2": "failed",
    }
    assert "Lovelace" not in stored_text(client, run.id)

    # A database error message quoting a value is not stored either.
    failing = client_factory(graph_source=ExplodingGraphSource(graph_source))
    results = failing.evaluate_run(run.id)

    assert statuses(result(results, "competency_question_execution")) == {
        "q1": "error",
        "q2": "error",
    }
    assert "Lovelace" not in stored_text(client, run.id)


def test_a_query_that_fails_fails_its_question_with_the_error_type_only(
    client_factory, support_kg, graph_source
):
    seed_support_graph(graph_source)
    client = client_factory(graph_source=ExplodingGraphSource(graph_source))
    client.register_use_case(support_kg, [stetiq.CompetencyQuestion("q", "Who?", query=WHO_OPENED)])

    run = run_once(client)

    execution = result(client.get_run_evaluation_results(run.id), "competency_question_execution")
    [detail] = execution.details
    assert detail.metric == "failed_questions"
    assert detail.data == {
        "status": "error",
        "rows": 0,
        "check": "non_empty",
        "error": "RuntimeError",
    }
    assert execution.metrics["failed_questions"] == 1


def test_run_level_evaluation_can_be_re_run_on_demand(client, support_kg, graph_source):
    seed_support_graph(graph_source)
    graph_source.add_query_result(NO_AGENTS, [])
    client.register_use_case(
        support_kg, [stetiq.CompetencyQuestion("agents", "Which agents?", query=NO_AGENTS)]
    )
    run = run_once(client)
    graph_source.add_query_result(NO_AGENTS, [{"name": "Grace"}])

    results = client.evaluate_run(run.id)

    assert [r.evaluator for r in results] == [
        "competency_question_execution",
        "conformance",
        "observed_schema",
    ]
    assert statuses(result(results, "competency_question_execution")) == {"agents": "passed"}
    assert result(results, "conformance").metrics["score"] == 5 / 6


def test_re_running_judges_against_a_chosen_use_case_version(client, support_kg, graph_source):
    seed_support_graph(graph_source)
    graph_source.add_query_result(WHO_OPENED, [{"name": "Ada"}])
    first = client.register_use_case(
        support_kg, [stetiq.CompetencyQuestion("a", "Who?", query=WHO_OPENED)]
    )
    client.add_competency_question(
        support_kg, stetiq.CompetencyQuestion("b", "Who else?", query=WHO_OPENED)
    )
    run = run_once(client)
    assert (
        result(
            client.get_run_evaluation_results(run.id), "competency_question_execution"
        ).use_case_version
        == 2
    )

    results = client.evaluate_run(run.id, use_case_version=first.number)

    execution = result(results, "competency_question_execution")
    assert execution.use_case_version == 1
    assert statuses(execution) == {"a": "passed"}


def test_without_a_use_case_no_competency_questions_are_executed(client, support_kg, graph_source):
    seed_support_graph(graph_source)

    run = run_once(client)

    assert [r.evaluator for r in client.get_run_evaluation_results(run.id)] == [
        "conformance",
        "observed_schema",
    ]


class TicketShare(stetiq.ConstructionRunEvaluator):
    name = "ticket_share"

    def evaluate(self, run):
        [count] = run.graph_source.execute_read(OPEN_COUNT)
        nodes = sum(n.count for n in run.observation.schema.node_types)
        return stetiq.Evaluation(
            metrics={
                "ticket_share": count["tickets"] / nodes,
                "declared_version": run.declared_ontology.number,
            }
        )


def test_custom_run_evaluators_run_at_run_end_and_on_demand(client, support_kg, graph_source):
    seed_support_graph(graph_source)
    graph_source.add_query_result(OPEN_COUNT, [{"tickets": 1}])
    client.register_evaluator(TicketShare())

    run = run_once(client)

    share = result(client.get_run_evaluation_results(run.id), "ticket_share")
    assert share.metrics == {"ticket_share": 1 / 3, "declared_version": 1}

    graph_source.add_query_result(OPEN_COUNT, [{"tickets": 3}])
    share = result(client.evaluate_run(run.id), "ticket_share")
    assert share.metrics["ticket_share"] == 1.0


def test_a_failing_custom_run_evaluator_raises_but_the_run_and_other_results_stay(
    client, support_kg, graph_source
):
    class Broken(stetiq.ConstructionRunEvaluator):
        name = "broken"

        def evaluate(self, run):
            raise ValueError("boom")

    seed_support_graph(graph_source)
    client.register_evaluator(Broken())

    with (
        pytest.raises(stetiq.EvaluatorError, match="broken"),
        client.start_run(support_kg, ontology_version=1),
    ):
        pass

    [run] = client.list_runs(support_kg)
    assert run.status == "finished"
    assert {r.evaluator for r in client.get_run_evaluation_results(run.id)} == {
        "conformance",
        "observed_schema",
    }


@pytest.mark.parametrize(
    "name", ["conformance", "observed_schema", "competency_question_execution"]
)
def test_run_level_built_in_names_are_reserved(client, name):
    class Impostor(stetiq.ConstructionRunEvaluator):
        def evaluate(self, run):
            return stetiq.Evaluation(metrics={})

    impostor = Impostor()
    impostor.name = name
    with pytest.raises(stetiq.EvaluatorError):
        client.register_evaluator(impostor)


def test_an_aborted_run_has_no_observation_to_evaluate(client, support_kg, graph_source):
    run = client.start_run(support_kg, ontology_version=1)
    run.fail()

    assert client.get_run_evaluation_results(run.id) == []
    with pytest.raises(stetiq.EvaluatorError, match="no Observation"):
        client.evaluate_run(run.id)


def test_a_run_failed_by_strict_evolution_mode_is_still_evaluated(client, support_kg, graph_source):
    client.set_evolution_mode(support_kg, "strict")
    seed_support_graph(graph_source)
    graph_source.add_node(["Agent"], {})

    run = run_once(client)

    assert run.status == "failed"
    conformance = result(client.get_run_evaluation_results(run.id), "conformance")
    assert conformance.metrics["undeclared"] == 1


# --- Gates ------------------------------------------------------------------------------

ALL_CQS_PASS = """
gates:
  - name: all-cqs-pass
    check: metric
    evaluator: competency_question_execution
    metric: failed_questions
    max: 0
  - name: enough-tickets
    check: metric
    evaluator: observed_schema
    metric: nodes
    min: 3
"""


def test_a_metric_gate_can_reference_run_level_results(client, support_kg, graph_source):
    seed_support_graph(graph_source)
    graph_source.add_query_result(NO_AGENTS, [])
    client.register_use_case(
        support_kg, [stetiq.CompetencyQuestion("agents", "Which agents?", query=NO_AGENTS)]
    )
    run = run_once(client)

    by_run = client.evaluate_gates(support_kg, ALL_CQS_PASS, run=run.id)
    by_version = client.evaluate_gates(support_kg, ALL_CQS_PASS, version=1)

    for gated in (by_run, by_version):
        assert [o.gate.name for o in gated.failed] == ["all-cqs-pass"]
        assert gated.failed[0].reasons == (
            "competency_question_execution.failed_questions = 1 > max 0",
            "agents: empty result",
        )

    graph_source.add_query_result(NO_AGENTS, [{"name": "Grace"}])
    client.evaluate_run(run.id)
    assert client.evaluate_gates(support_kg, ALL_CQS_PASS, run=run.id).passed
