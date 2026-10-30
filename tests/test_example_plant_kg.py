"""The plant maintenance example (examples/plant-kg) runs end to end, offline, and tells
the story its README promises: declare, build, evaluate, improve, gate, promote, operate.

It drives the SDK in local mode over a temporary SQLite tracking database and the
example's file-backed graph store, with the deterministic rule-based extractors (the
Claude extractor needs the `claude` CLI and is not exercised here)."""

import importlib
import sys
from pathlib import Path

import pytest

EXAMPLE_DIR = Path(__file__).resolve().parent.parent / "examples" / "plant-kg"


@pytest.fixture(scope="module")
def demo(tmp_path_factory):
    workspace = tmp_path_factory.mktemp("plant-kg")
    sys.path.insert(0, str(EXAMPLE_DIR))
    try:
        module = importlib.import_module("demo")
        return module.run_demo(
            tracking_uri=f"sqlite:///{workspace / 'stetiq.db'}",
            graph_file=workspace / "plant.json",
            llm_cache=workspace / "llm-cache",
            extractor="rules",
            quiet=True,
        )
    finally:
        sys.path.remove(str(EXAMPLE_DIR))


KG = "plant-maintenance"


def result(results, evaluator):
    [found] = [r for r in results if r.evaluator == evaluator]
    return found


def test_the_initial_ontology_cannot_answer_every_competency_question(demo):
    answerability = result(demo.priya.get_evaluation_results(KG, 1), "structural_answerability")
    assert answerability.metrics["questions"] == 8
    assert answerability.metrics["answerable_questions"] == 5
    statuses = {d.item: d.data["status"] for d in answerability.details}
    assert statuses["root-causes"] == "unanswerable"
    assert statuses["downtime-by-kind"] == "unanswerable"
    assert statuses["repeat-faults"] == "unmapped"


def test_the_first_run_shows_the_gaps_and_proposes_a_candidate(demo):
    run = demo.run1
    assert run.status == "finished"
    assert run.ontology_version == 1
    assert run.conformance.score == pytest.approx(30 / 33)
    assert {(str(m.kind), m.subject) for m in run.conformance.mismatches} == {
        ("required_missing", "Technician.badge"),
        ("undeclared", "WorkOrder.downtime_minutes"),
        ("absent", "SUPPLIED_BY"),
    }
    assert run.candidate_version == 2
    assert demo.priya.get_ontology_version(KG, 2).origin == "run"

    results = demo.priya.get_run_evaluation_results(run.id)
    execution = result(results, "competency_question_execution")
    assert execution.metrics["pass_ratio"] == pytest.approx(4 / 6)
    failed = {d.item for d in execution.details if d.data["status"] != "passed"}
    assert failed == {"downstream-of-press", "root-causes"}
    assert result(results, "report_coverage").metrics["coverage"] == 0.875


def test_the_candidate_fails_most_gates(demo):
    gates = demo.gates_candidate
    assert gates.ontology_version == 2
    assert {o.gate.name for o in gates.outcomes if o.passed} == {
        "no-breaking-changes",
        "no-type-collapses",
    }
    assert {o.gate.name for o in gates.failed} == {
        "graph-conforms",
        "questions-answerable",
        "questions-run",
        "no-orphans",
        "consistent-constraints",
        "documented",
        "reports-cover-orders",
    }


def test_the_revised_ontology_and_pipeline_pass_every_gate_and_get_promoted(demo):
    client = demo.priya
    assert client.diff_ontology_versions(KG, 1, 3).classification == "additive"
    answerability = result(client.get_evaluation_results(KG, 3), "structural_answerability")
    assert answerability.use_case_version == 2
    assert answerability.metrics["answerable_questions"] == 8
    assert answerability.metrics["questions"] == 9

    assert demo.run2.conformance.score == 1.0
    execution = result(
        client.get_run_evaluation_results(demo.run2.id), "competency_question_execution"
    )
    assert execution.metrics == {
        "questions": 7,
        "passed_questions": 7,
        "failed_questions": 0,
        "skipped_questions": 2,
        "pass_ratio": 1.0,
    }
    assert demo.nightly.status == "finished"
    assert demo.nightly.params["entry_point.exit_code"] == "0"
    assert demo.nightly.conformance.score == 1.0

    comparison = client.compare_runs([demo.run1.id, demo.run2.id, demo.nightly.id])
    assert comparison.ontology_versions == (1, 3, 3)
    assert comparison.metrics["reports_read"] == (7.0, 8.0, None)

    gold = result(client.get_evaluation_results(KG, 3), "gold_alignment")
    assert gold.parameters == {"reference_knowledge_graph": "plant-gold", "reference_version": 1}
    assert gold.metrics["precision"] == 1.0
    assert gold.metrics["recall"] == pytest.approx(31 / 35)

    assert demo.gates_revised.passed
    assert client.get_contract_version(KG).number == 3
    production = [p for p in client.list_promotions(KG) if p.alias == "production"]
    assert [(p.from_version, p.to_version, p.actor, p.gate_result) for p in production] == [
        (None, 1, "stetiq", None),
        (1, 3, "ci-bot", "passed"),
    ]


def test_an_observation_between_runs_finds_the_hand_edits_as_drift(demo):
    drift = demo.drift
    assert drift is not None
    assert drift.ontology_version == 3
    assert {(str(f.kind), f.subject) for f in drift.structural} == {
        ("undeclared", "SparePart"),
        ("undeclared", "SparePart.sku"),
    }
    follow_ups = next(f for f in drift.statistical if f.subject == "FollowUp")
    assert (follow_ups.previous_count, follow_ups.observed_count) == (12, 6)
    # Drift never creates an Ontology Version.
    assert [v.number for v in demo.priya.list_ontology_versions(KG)] == [1, 2, 3, 4]


def test_strict_evolution_mode_fails_a_run_that_introduces_concepts(demo):
    assert demo.strict_run.status == "failed"
    assert demo.strict_run.candidate_version is None
    undeclared = {
        m.subject for m in demo.strict_run.conformance.mismatches if str(m.kind) == "undeclared"
    }
    assert "Sensor" in undeclared and "HAS_SENSOR" in undeclared


def test_a_breaking_proposal_is_rejected_by_the_gates_but_never_promoted(demo):
    gates = demo.gates_proposal
    assert gates.ontology_version == 4
    [diff_gate] = [o for o in gates.outcomes if o.gate.name == "no-breaking-changes"]
    assert not diff_gate.passed
    assert any("WorkOrder" in reason and "breaking" in reason for reason in diff_gate.reasons)
    assert demo.priya.get_contract_version(KG).number == 3
    assert demo.priya.get_evolution_mode(KG) == "evolving"
