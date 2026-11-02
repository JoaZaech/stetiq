"""The plant maintenance example (examples/plant-kg) replays its three recorded Claude
rounds offline and tells the story its README promises: v1 is promoted; prompt v2 is
better by the evals but breaks the reliability dashboard, so it stays unpromoted; the
fix binds `WorkOrder.kind` to a Vocabulary and is promoted.

It drives the SDK in local mode over a temporary SQLite tracking database and the
example's file-backed graph store, reading Claude's answers from the committed
llm-cache/ only: the `claude` CLI is never started."""

import importlib
import json
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


def test_prompt_v2s_evals_line_leaves_out_the_rows_the_consumer_gate_flagged(demo):
    # downtime-by-kind gains a row only because `corrective` is a new kind: that is the
    # drift the dashboard's Consumer Gate caught, not an eval gain.
    demo_module = importlib.import_module("demo")
    [line] = demo_module.eval_lines(demo.priya, demo.rounds["v1"].run, demo.rounds["v2"])
    assert line.strip() == (
        "Evals v1 → prompt v2: report_coverage 1.00 → 1.00; "
        "rows outside triage-breakdowns: parts-suppliers 0 → 5"
    )


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


# --- the agent step: a coding agent reads the red round 2 through `stetiq mcp` ---


@pytest.fixture(scope="module")
def round_2_context(tmp_path_factory):
    """The Run Context a coding agent gets from `stetiq mcp` once round 2 is red: the
    replay stops before the committed fix, and the `run_context` tool is called
    in-process with no version, so it reads the Contract Alias's (v1)."""
    mcp = pytest.importorskip("mcp")
    import anyio

    from stetiq.mcp_server import create_server

    demo = _run_demo(tmp_path_factory.mktemp("plant-kg-round-2"), until="v2")
    assert "fix" not in demo.rounds

    async def call():
        async with mcp.Client(create_server(demo.priya)) as session:
            return await session.call_tool("run_context", {"knowledge_graph": KG})

    result = anyio.run(call)
    assert not result.is_error
    return json.loads(result.content[0].text)


def _verdict(results, consumer):
    [verdict] = [r for r in results if r["consumer"] == consumer]
    return verdict


def test_the_agent_reads_v1_with_kind_as_a_plain_string(round_2_context):
    assert round_2_context["ontology_version"]["number"] == 1
    # `kind` is an unbound string in v1: what the committed fix tightens to a Vocabulary.
    [work_order] = [
        n
        for n in round_2_context["ontology_version"]["ontology"]["node_types"]
        if n["label"] == "WorkOrder"
    ]
    assert {"name": "kind", "type": "STRING"} in work_order["properties"]


def test_the_last_attempt_is_prompt_v2s_run_and_its_additive_candidate(round_2_context):
    attempt = round_2_context["last_attempt"]
    assert (attempt["status"], attempt["ontology_version"], attempt["candidate_version"]) == (
        "finished",
        1,
        2,
    )
    assert attempt["added"]["classification"] == "additive"
    assert [(c["concept"], c["kind"]) for c in attempt["added"]["changes"]] == [
        ("Supplier", "added"),
        ("SUPPLIED_BY", "added"),
    ]


def test_the_last_attempt_fails_the_reliability_dashboards_consumer_gate(round_2_context):
    dashboard = _verdict(
        round_2_context["last_attempt"]["consumer_gate_results"], "reliability-dashboard"
    )
    assert dashboard["status"] == "failed"
    [outcome] = dashboard["outcomes"]
    assert (outcome["gate"]["name"], outcome["passed"]) == ("triage-rows-hold", False)
    [finding] = outcome["findings"]
    assert (finding["task"], finding["competency_question"]) == (
        "triage-breakdowns",
        "breakdown-technicians",
    )
    assert (finding["before"], finding["after"], finding["limit"]) == (6, 4, 0.1)
    assert outcome["reasons"] == [
        "triage-breakdowns / breakdown-technicians: 6 → 4 rows (−33.3%, limit −10%)"  # noqa: RUF001 - the minus sign stetiq writes
    ]


def test_the_last_attempt_passes_the_maintenance_assistants_consumer_gate(round_2_context):
    assistant = _verdict(
        round_2_context["last_attempt"]["consumer_gate_results"], "maintenance-assistant"
    )
    assert assistant["status"] == "passed"
    [outcome] = assistant["outcomes"]
    assert outcome["findings"] == []
    assert outcome["new_questions"] == ["parts-suppliers"]


def test_the_last_attempt_passes_the_front_gate(round_2_context):
    gate = round_2_context["last_attempt"]["gate_result"]
    assert gate["status"] == "passed"
    assert all(o["passed"] for o in gate["outcomes"])


def test_the_last_attempts_rows_point_at_a_new_kind(round_2_context):
    # The Ontology Diff only adds Supplier: the relabelling is in the data, which stetiq
    # never reads. What points at `kind` is the rows: the breakdowns lost from
    # breakdown-technicians reappear as a third `kind` group in downtime-by-kind.
    after = {q["id"]: q["rows"] for q in round_2_context["last_attempt"]["competency_questions"]}
    before = {
        q["id"]: q["execution"]["rows"]
        for q in round_2_context["competency_questions"]
        if q["execution"]
    }
    assert (before["breakdown-technicians"], after["breakdown-technicians"]) == (6, 4)
    assert (before["downtime-by-kind"], after["downtime-by-kind"]) == (2, 3)
    assert after["parts-suppliers"] == 5


def test_v1s_run_passed_its_gate_and_was_never_consumer_gated(round_2_context):
    # The baseline run, which `run` still stands for, was gated but never Consumer-gated:
    # "not evaluated", never a pass.
    assert round_2_context["gate_result"]["status"] == "passed"
    assert round_2_context["consumer_gate_results"] == [
        {"consumer": "maintenance-assistant", "status": "not_evaluated"},
        {"consumer": "reliability-dashboard", "status": "not_evaluated"},
    ]
