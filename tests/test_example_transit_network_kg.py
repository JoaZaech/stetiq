"""The city-transit example (examples/transit-network-kg) runs end to end, offline, and
tells the story its README promises through the stetiq CLI alone: declare, build under
strict and evolving Evolution Mode, gate and promote, observe Drift, and tell a failed
Gate (exit 3) from a broken config (exit 1).

Every act is a `stetiq` command run in-process with typer's CliRunner over a temporary
SQLite tracking database and the example's file-backed graph database. The test reads the
exit codes and outputs the demo recorded, the way a CI job would."""

import importlib.util
import sys
from pathlib import Path

import pytest

import stetiq

EXAMPLE_DIR = Path(__file__).resolve().parent.parent / "examples" / "transit-network-kg"
MODULE_NAME = "example_transit_network_kg_demo"
KG = "city-transit"


@pytest.fixture(scope="module")
def demo(tmp_path_factory):
    workspace = tmp_path_factory.mktemp("transit-network-kg")
    spec = importlib.util.spec_from_file_location(MODULE_NAME, EXAMPLE_DIR / "demo.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[MODULE_NAME] = module
    sys.path.insert(0, str(EXAMPLE_DIR))
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path.remove(str(EXAMPLE_DIR))
    return module.run_demo(
        tracking_uri=f"sqlite:///{workspace / 'stetiq.db'}",
        graph_file=workspace / "transit.json",
        quiet=True,
    )


def test_act_1_declares_the_knowledge_graph_and_judges_the_use_case_against_v1(demo):
    for name in ("kg-create", "bind-source", "use-case-register", "evolution-strict"):
        assert demo.step(name).exit_code == 0, name
    assert "Ontology Version 1" in demo.step("kg-create").output
    assert "7 Competency Questions" in demo.step("use-case-register").output
    answerability = demo.step("evaluations-v1").metrics("structural_answerability")
    assert answerability["questions"] == 7
    assert answerability["answerable_questions"] == 5
    assert answerability["unanswerable_questions"] == 1
    assert answerability["unmapped_questions"] == 1
    assert "accessible-stops [unanswerable_questions]" in demo.step("evaluations-v1").output
    assert demo.step("evolution-strict").output == "strict"


def consumers_of(use_case_version):
    return {
        c.id: (c.name, c.kind, {t.id: set(t.competency_questions) for t in c.tasks})
        for c in use_case_version.use_case.consumers
    }


def test_act_1_registers_the_consumers_and_the_tasks_they_need_answered(demo):
    # stops-on-route and accessible-stops each serve two Tasks; average-dwell-time none.
    latest = stetiq.Client(demo.tracking_uri).get_use_case_version(KG)
    assert latest.number == 1
    assert consumers_of(latest) == {
        "journey-planner": (
            "Journey planner",
            "application",
            {"plan-journey": {"stops-on-route", "transfers-at-stop", "accessible-stops"}},
        ),
        "timetable-team": (
            "Timetable team",
            "team",
            {"publish-timetable": {"trips-per-service", "stops-on-route"}},
        ),
        "step-free-report": (
            "Step-free access report",
            "report",
            {"audit-step-free-stops": {"accessible-stops"}},
        ),
        "operations-dashboard": (
            "Operations dashboard",
            "dashboard",
            {"depots-and-zones": {"depot-of-route", "stops-per-zone"}},
        ),
    }


def test_act_2_strict_evolution_mode_fails_the_run_and_the_cli_exits_1(demo):
    strict = demo.step("run-strict")
    assert strict.exit_code == 1
    assert (
        f"Construction Run {demo.runs['run-strict']} failed (Ontology Version 1)" in strict.output
    )
    assert "Conformance: 0.926" in strict.output
    assert (
        "new Concepts observed: Stop.wheelchairBoarding, Trip.bikesAllowed, PARENT_STATION"
        in strict.output
    )
    listed = demo.step("runs-list-after-strict")
    assert listed.exit_code == 0
    assert f"{demo.runs['run-strict']}  failed" in listed.output
    # The Entry Point itself exited 0: it is the Evolution Mode that failed the run.
    assert "param  entry_point.exit_code = 0" in demo.step("runs-get-strict").output


def test_act_2_evolving_mode_yields_candidate_v2_as_an_additive_diff(demo):
    assert demo.step("evolution-evolving").output == "evolving"
    evolving = demo.step("run-evolving")
    assert evolving.exit_code == 0
    assert "Candidate: Ontology Version 2" in evolving.output
    diff = demo.step("diff-1-2")
    assert diff.exit_code == 0
    # Additive changes hit no Consumer.
    assert diff.lines[-2:] == ["Overall: additive", "Consumer impact: none"]
    assert [line.split()[2] for line in diff.lines[:-2]] == [
        "Stop.wheelchairBoarding",
        "Trip.bikesAllowed",
        "PARENT_STATION",
    ]


def test_act_2_naming_conventions_flag_the_feed_spelling_in_v2_and_nothing_in_v3(demo):
    v2 = demo.step("evaluate-v2")
    assert v2.exit_code == 0
    naming = v2.metrics("naming_conventions")
    assert naming["violations"] == 2
    assert naming["checked"] == 46
    assert naming["compliance"] == pytest.approx(44 / 46, abs=1e-6)
    assert "  - Stop.wheelchairBoarding [violations]: property name is not snake_case" in v2.lines
    assert "  - Trip.bikesAllowed [violations]: property name is not snake_case" in v2.lines

    assert "Ontology Version 3" in demo.step("register-v3").output
    v3 = demo.step("evaluate-v3")
    assert v3.metrics("naming_conventions") == {"checked": 46, "compliance": 1, "violations": 0}
    assert v3.metrics("structural_answerability")["answerable_ratio"] == pytest.approx(6 / 7)
    assert demo.step("diff-1-3").lines[-2:] == ["Overall: additive", "Consumer impact: none"]


def test_act_3_gates_reject_the_candidate_pass_v3_and_ci_promotes_production(demo):
    rejected = demo.step("gate-v2")
    assert rejected.exit_code == 3
    assert {name for name, passed in rejected.gates().items() if not passed} == {
        "graph-conforms",
        "names-follow-conventions",
        "questions-answerable",
    }
    assert "      - naming_conventions.violations = 2 > max 0" in rejected.lines

    assert demo.step("run-v3").exit_code == 0
    assert "Conformance: 1.000" in demo.step("run-v3").output
    passed = demo.step("gate-v3")
    assert passed.exit_code == 0
    assert passed.gates() == dict.fromkeys(
        [
            "no-breaking-changes",
            "graph-conforms",
            "names-follow-conventions",
            "questions-answerable",
            "no-isolated-node-types",
            "no-type-collapses",
        ],
        True,
    )
    assert passed.lines[-1] == f"All 6 Gates passed for {KG} Ontology Version 3"

    assert demo.step("alias-set-production").output == "Alias production -> Ontology Version 3"
    log = demo.step("alias-log")
    rows = [line.split()[:5] for line in log.lines[1:]]
    assert rows == [
        ["production", "-", "1", "stetiq", "-"],
        ["production", "1", "3", "ci-bot", "passed"],
    ]


def test_act_4_no_drift_between_runs_and_the_september_feed_passes_the_gates(demo):
    clean = demo.step("observe-clean")
    assert clean.exit_code == 0
    assert clean.lines[-1] == "No Drift"
    september = demo.step("run-september")
    assert september.exit_code == 0
    assert "(Ontology Version 3)" in september.output
    assert "Conformance: 1.000" in september.output
    assert "Candidate" not in september.output
    gate = demo.step("gate-run-september")
    assert gate.exit_code == 0
    assert gate.lines[-1] == f"All 6 Gates passed for {KG} run {demo.runs['run-september']}"


def test_act_4_a_partial_export_conforms_but_fails_the_count_drop_gate(demo):
    partial = demo.step("run-partial")
    assert partial.exit_code == 0
    assert "Conformance: 1.000" in partial.output
    gate = demo.step("gate-run-partial")
    assert gate.exit_code == 3
    assert [name for name, passed in gate.gates().items() if not passed] == ["no-type-collapses"]
    assert "      - node type Service: 3 -> 1 (-66.7%)" in gate.lines
    assert "      - relationship type RUNS_ON: 45 -> 27 (-40.0%)" in gate.lines
    assert gate.lines[-1] == f"1 of 6 Gates failed for {KG} run {demo.runs['run-partial']}"


def test_act_4_a_hand_edit_is_drift_and_observe_exits_3(demo):
    assert demo.stop_times_deleted == 164  # 40% of 410
    drifted = demo.step("observe-after-hand-edit")
    assert drifted.exit_code == 3
    assert "Drift: 3 finding(s) against production (Ontology Version 3)" in drifted.output
    assert set(drifted.findings()) == {
        ("count_drop", "node_type", "StopTime"),
        ("count_drop", "relationship_type", "AT_STOP"),
        ("count_drop", "relationship_type", "HAS_STOP_TIME"),
    }
    assert "count dropped from 410 to 246 (-40%)" in drifted.output
    events = demo.step("drift-list")
    assert events.exit_code == 0
    [row] = events.lines[1:]  # the clean Observation raised no event
    assert row.split()[1:4] == ["production@3", "0", "3"]


def test_act_5_a_broken_config_exits_1_not_3_and_the_runs_compare(demo):
    broken = demo.step("gate-broken-config")
    assert broken.exit_code == 1
    assert broken.output == "error: Gate 'graph-conforms': missing 'min_score'"

    compare = demo.step("runs-compare")
    assert compare.exit_code == 0
    rows = {line.split("  ")[0]: line.split()[1:] for line in compare.lines}
    assert rows["ontology_version"] == ["1", "1", "3", "3", "3"]
    assert rows["conformance"] == ["0.925926", "0.925926", "1", "1", "1"]
    assert rows["observed_schema.nodes"] == ["555", "555", "555", "542", "540"]
    assert rows["competency_question_execution.pass_ratio"] == ["0.8", "0.8", "1", "0.8", "0.8"]
    assert [line.split()[:2] for line in demo.step("ontology-list").lines[1:]] == [
        ["1", "registered"],
        ["2", "run"],
        ["3", "registered"],
    ]
