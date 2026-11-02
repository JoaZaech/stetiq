"""The plant maintenance example (examples/plant-kg) replays its three recorded Claude
rounds offline and tells the story its README promises: v1 is promoted; prompt v2 is
better by the evals but breaks the reliability dashboard, so it stays unpromoted; the
fix binds `WorkOrder.kind` to a Vocabulary and is promoted.

It drives the SDK in local mode over a temporary SQLite tracking database and the
example's file-backed graph store, reading Claude's answers from the committed
llm-cache/ only: the `claude` CLI is never started."""

import importlib
from pathlib import Path

import pytest

EXAMPLE_DIR = Path(__file__).resolve().parent.parent / "examples" / "plant-kg"
KG = "plant-maintenance"


def _no_claude(*args, **kwargs):
    raise AssertionError("the demo called the claude CLI; the replay must stay offline")


def _run_demo(workspace: Path, **kwargs):
    with pytest.MonkeyPatch.context() as mp:
        mp.syspath_prepend(str(EXAMPLE_DIR))
        pipeline = importlib.import_module("pipeline")
        mp.setattr(pipeline.ClaudeExtractor, "_call", _no_claude)
        demo = importlib.import_module("demo")
        return demo.run_demo(
            tracking_uri=f"sqlite:///{workspace / 'stetiq.db'}",
            graph_file=workspace / "plant.json",
            quiet=True,
            **kwargs,
        )


@pytest.fixture(scope="module")
def workspace(tmp_path_factory):
    return tmp_path_factory.mktemp("plant-kg")


@pytest.fixture(scope="module")
def demo(workspace):
    return _run_demo(workspace)


def consumer_gate(round_result, consumer):
    [result] = [c for c in round_result.consumer_gates if c.consumer == consumer]
    [outcome] = result.outcomes
    return result, outcome


def test_v1_is_the_baseline_and_is_promoted(demo):
    v1 = demo.rounds["v1"]
    assert v1.run.status == "finished"
    assert v1.gates.passed
    assert v1.promoted
    assert v1.gates.ontology_version == 1
    # production points at v1 from the start; the passing Gate keeps it there.
    production = [p for p in demo.priya.list_promotions(KG) if p.alias == "production"]
    assert (production[0].from_version, production[0].to_version) == (None, 1)


def test_prompt_v2_proposes_an_additive_candidate_with_suppliers(demo):
    v2 = demo.rounds["v2"]
    assert v2.run.ontology_version == 1
    assert v2.run.candidate_version == 2
    diff = demo.priya.diff_ontology_versions(KG, 1, 2)
    assert diff.classification == "additive"
    assert [c.concept for c in diff.changes] == ["Supplier", "SUPPLIED_BY"]


def test_prompt_v2_passes_the_gate_and_fails_the_reliability_dashboard(demo):
    v2 = demo.rounds["v2"]
    assert v2.gates.passed
    dashboard, outcome = consumer_gate(v2, "reliability-dashboard")
    assert not dashboard.passed
    assert outcome.gate.name == "triage-rows-hold"
    [finding] = outcome.findings
    assert (finding.task, finding.competency_question) == (
        "triage-breakdowns",
        "breakdown-technicians",
    )
    assert (finding.before, finding.after, finding.limit) == (6, 4, 0.10)
    assert finding.change == pytest.approx(-1 / 3)


def test_prompt_v2_passes_the_maintenance_assistant_with_parts_suppliers_not_compared(demo):
    assistant, outcome = consumer_gate(demo.rounds["v2"], "maintenance-assistant")
    assert assistant.passed
    assert outcome.findings == ()
    assert outcome.new_questions == ("parts-suppliers",)


def test_prompt_v2_stays_unpromoted(demo):
    assert not demo.rounds["v2"].promoted
    production = [p.to_version for p in demo.priya.list_promotions(KG) if p.alias == "production"]
    assert 2 not in production


def test_the_fix_binds_kind_passes_every_check_and_is_promoted(demo):
    fix = demo.rounds["fix"]
    assert fix.run.ontology_version == 3
    assert fix.run.candidate_version is None  # the graph is what the fix declares
    assert fix.gates.passed
    [diff_gate] = [o for o in fix.gates.outcomes if o.gate.name == "no-breaking-changes"]
    assert diff_gate.reasons == (
        "binding WorkOrder.kind -> WorkOrderKind accepted: all observed values are in the "
        "Vocabulary",
    )
    assert all(c.passed for c in fix.consumer_gates)
    assert sorted(c.consumer for c in fix.consumer_gates) == [
        "maintenance-assistant",
        "reliability-dashboard",
    ]
    _, dashboard = consumer_gate(fix, "reliability-dashboard")
    assert dashboard.findings == ()
    assert fix.promoted
    assert demo.priya.get_contract_version(KG).number == 3
    production = [p for p in demo.priya.list_promotions(KG) if p.alias == "production"]
    assert [(p.from_version, p.to_version, p.actor, p.gate_result) for p in production] == [
        (None, 1, "stetiq", None),
        (1, 3, "ci-bot", "passed"),
    ]


def test_a_cache_miss_is_an_error_naming_record(demo, workspace, monkeypatch, capsys):
    monkeypatch.syspath_prepend(str(EXAMPLE_DIR))
    pipeline = importlib.import_module("pipeline")
    monkeypatch.setattr(pipeline.ClaudeExtractor, "_call", _no_claude)
    monkeypatch.setenv("STETIQ_TRACKING_URI", demo.tracking_uri)
    empty = workspace / "empty-cache"
    empty.mkdir()

    exit_code = pipeline.main(
        [
            "--knowledge-graph",
            KG,
            "--ontology-version",
            "1",
            "--round",
            "v1",
            "--llm-cache",
            str(empty),
            "--graph",
            str(workspace / "miss.json"),
        ]
    )

    assert exit_code == 1
    error = capsys.readouterr().err
    assert "cache miss" in error and "rerun with --record" in error


def test_the_epilogue_records_drift_from_hand_edits(tmp_path):
    demo = _run_demo(tmp_path, epilogue=True)

    drift = demo.drift
    assert drift is not None
    assert drift.ontology_version == 3
    assert {(str(f.kind), f.subject) for f in drift.structural} == {
        ("undeclared", "SparePart"),
        ("undeclared", "SparePart.sku"),
    }
    follow_ups = next(f for f in drift.statistical if f.subject == "FollowUp")
    assert (follow_ups.previous_count, follow_ups.observed_count) == (12, 6)


def test_the_use_case_names_the_two_consumers_and_their_tasks(demo):
    latest = demo.priya.get_use_case_version(KG)
    consumers = {
        c.id: (c.kind, {t.id: list(t.competency_questions) for t in c.tasks})
        for c in latest.use_case.consumers
    }
    assert consumers == {
        "reliability-dashboard": (
            "dashboard",
            {"triage-breakdowns": ["breakdown-technicians", "downtime-by-kind"]},
        ),
        "maintenance-assistant": (
            "agent",
            {"explain-root-causes": ["parts-suppliers", "root-causes"]},
        ),
    }
