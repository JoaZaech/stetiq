"""Better by your evals, broken for your Consumer, fixed by the Ontology.

    cd examples/plant-kg
    uv run python demo.py              # replays three recorded Claude rounds, offline
    uv run python demo.py --epilogue   # ... then hand edits to the graph, and Drift
    uv run python demo.py --live       # calls Claude for real (needs the `claude` CLI)
    uv run stetiq ui                   # then browse the same verdicts

Everything is local: the tracking database is .stetiq/stetiq.db, the graph database
is the file .graphdb/plant.json (see graphdb.py). README.md tells the story.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, replace
from pathlib import Path

EXAMPLE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(EXAMPLE_DIR))

from evaluators import Documented, ReportCoverage  # noqa: E402
from graphdb import DEFAULT_DATABASE, PARTS_SUPPLIERS, LocalGraph  # noqa: E402
from pipeline import (  # noqa: E402
    DEFAULT_GRAPH_FILE,
    DEFAULT_MODEL,
    ROUNDS,
    ExtractionError,
    LlmMode,
    Round,
    run_round,
)

import stetiq  # noqa: E402
from stetiq import CompetencyQuestion, GraphSourceScope  # noqa: E402
from stetiq.config import load_config  # noqa: E402
from stetiq.drift import thresholds_from_config  # noqa: E402

KG = "plant-maintenance"
SCOPE = GraphSourceScope(database=DEFAULT_DATABASE)
CONFIG = EXAMPLE_DIR / "stetiq.yaml"
ONTOLOGY = EXAMPLE_DIR / "ontology"
USE_CASE = EXAMPLE_DIR / "use-case.yaml"
DEFAULT_TRACKING_URI = f"sqlite:///{EXAMPLE_DIR / '.stetiq' / 'stetiq.db'}"

DESCRIPTION = """Maintenance history of the two production lines: **work orders** from the CMMS,
the **machines** and **lines** from the asset register, and what Claude reads out of the
technicians' free-text reports (components, root causes, follow-ups, part suppliers).

Built by `examples/plant-kg/pipeline.py`; the Consumers and their Competency Questions
are in `use-case.yaml`."""

WITHOUT_STETIQ = """\
Without stetiq: the plant's pipeline has Claude read the technicians' reports into a
knowledge graph. One pull request brings a better prompt (it also pulls out who supplied
each replacement part) and takes in the export of Line 2's new maintenance system. Every
check the team runs passes, so it ships. But the new system's order types call a
breakdown `corrective`, the pipeline copies `kind` from the export as it always has, and
the reliability dashboard counts breakdowns with `kind = 'breakdown'`. Nothing errors:
the dashboard quietly drops Line 2's breakdowns (CNC-04's worn spindle bearing,
Lathe-02's sticking chuck valve) from the morning stand-up. Claude read them right; the
new export's codes broke the dashboard.

With stetiq, three recorded Claude rounds:"""

ROUND_LABEL: dict[Round, str] = {"v1": "v1", "v2": "prompt v2", "fix": "fix"}


@dataclass(frozen=True)
class RoundResult:
    """What one round recorded (the test reads it back)."""

    round: Round
    run: stetiq.ConstructionRun
    gates: stetiq.GateResult
    consumer_gates: tuple[stetiq.ConsumerGateResult, ...]  # empty for the baseline
    promoted: bool

    @property
    def consumer_gates_passed(self) -> bool:
        return all(r.passed for r in self.consumer_gates)


class Demo:
    """The state the walkthrough builds up (the test reads it back)."""

    def __init__(
        self,
        *,
        tracking_uri: str,
        graph_file: Path,
        model: str,
        record: frozenset[Round] = frozenset(),
        live: bool = False,
        quiet: bool = False,
    ) -> None:
        self.tracking_uri = tracking_uri
        self.graph = LocalGraph(graph_file)
        self.quiet = quiet
        self.record = record
        self.live = live
        self.rounds: dict[Round, RoundResult] = {}
        # Two users of the same tracking database: the engineer who builds the graph and
        # the CI job that gates and promotes. The audit log names each one.
        self.priya = stetiq.Client(tracking_uri, graph_source=self.graph, actor="priya.natarajan")
        self.priya.register_evaluator(Documented())
        self.priya.register_evaluator(ReportCoverage())
        self.ci = stetiq.Client(tracking_uri, graph_source=self.graph, actor="ci-bot")
        self.model = model

    def say(self, *lines: str) -> None:
        if not self.quiet:
            print(*lines, sep="\n", flush=True)

    # --- setup ------------------------------------------------------------------------

    def declare(self) -> None:
        client = self.priya
        client.create_knowledge_graph(KG, ontology=ONTOLOGY / "v1.yaml")
        client.set_knowledge_graph_description(KG, DESCRIPTION)
        client.bind_graph_source(KG, SCOPE)
        client.register_use_case(KG, USE_CASE)

    # --- one round --------------------------------------------------------------------

    def construct(
        self, round_: Round, *, ontology_version: int | None = None
    ) -> stetiq.ConstructionRun:
        """Run the pipeline's `round_` as an SDK-instrumented Construction Run (see
        `pipeline.run_round`). Its Declared Ontology is `ontology_version`, else the
        Contract Alias's version."""
        mode: LlmMode = "record" if round_ in self.record else "live" if self.live else "replay"
        run = run_round(
            self.priya,
            KG,
            round_,
            graph=self.graph,
            ontology_version=ontology_version,
            model=self.model,
            mode=mode,
        )
        if run.ignored_definitions:
            self.say(
                f"            ignored Definitions (not added by the run): "
                f"{', '.join(run.ignored_definitions)}"
            )
        return run

    def gate(
        self, round_: Round, run: stetiq.ConstructionRun, *, consumers: bool, promote: bool
    ) -> RoundResult:
        if run.candidate_version is not None:
            # The custom Ontology Version Evaluator (`documented`) on the new Candidate;
            # the built-ins ran when it was registered.
            self.priya.evaluate(KG, run.candidate_version)
        gates = self.ci.evaluate_gates(KG, CONFIG, run=run.id)
        consumer_gates = tuple(self.ci.evaluate_consumer_gates(KG, run=run.id)) if consumers else ()
        result = RoundResult(round_, run, gates, consumer_gates, False)
        if promote and gates.passed and result.consumer_gates_passed:
            self.ci.set_alias(KG, "production", gates.ontology_version)
            result = RoundResult(round_, run, gates, consumer_gates, True)
        self.rounds[round_] = result
        self.say(summary_line(result))
        self.say(*detail_lines(result))
        return result

    def round_v1(self) -> RoundResult:
        run = self.construct("v1")
        return self.gate("v1", run, consumers=False, promote=True)

    def declare_parts_suppliers(self) -> stetiq.UseCaseVersion:
        """Before prompt v2: the maintenance assistant's Task now needs to know which
        suppliers' components keep failing, a reason for the pipeline to add Supplier."""
        current = self.priya.get_use_case_version(KG).use_case
        question = CompetencyQuestion(
            id="parts-suppliers",
            question="Which suppliers' components keep failing?",
            query=PARTS_SUPPLIERS.strip(),
        )
        consumers = tuple(
            replace(
                c,
                tasks=tuple(
                    replace(t, competency_questions=(*t.competency_questions, question.id))
                    if t.id == "explain-root-causes"
                    else t
                    for t in c.tasks
                ),
            )
            for c in current.consumers
        )
        return self.priya.register_use_case(
            KG,
            replace(
                current,
                competency_questions=(*current.competency_questions, question),
                consumers=consumers,
            ),
        )

    def round_v2(self) -> RoundResult:
        self.declare_parts_suppliers()
        run = self.construct("v2")
        result = self.gate("v2", run, consumers=True, promote=False)
        self.say(*eval_lines(self.priya, self.rounds["v1"].run, run))
        if run.candidate_version is not None:
            diff = self.priya.diff_ontology_versions(KG, 1, run.candidate_version)
            self.say(
                f"            Candidate v{run.candidate_version}: {diff.classification} Ontology Diff "
                f"({', '.join(sorted({c.concept for c in diff.changes}))})"
            )
        return result

    def round_fix(self) -> RoundResult:
        fix = self.priya.register_ontology(KG, ONTOLOGY / "fix.yaml")
        run = self.construct("fix", ontology_version=fix.number)
        return self.gate("fix", run, consumers=True, promote=True)

    # --- epilogue: Drift --------------------------------------------------------------

    def epilogue(self) -> None:
        self.say(
            "",
            "Epilogue: someone edits the graph database by hand (adds SparePart nodes, deletes",
            "the done follow-ups), and the next Observation outside any run records Drift.",
        )
        thresholds = thresholds_from_config(load_config(CONFIG))
        self.priya.observe(KG, thresholds=thresholds)
        for sku in ("SKF-6205", "PKR-H2-500", "FST-VUVG-L10"):
            self.graph.add_node(["SparePart"], {"sku": sku}, database=SCOPE.database)
        self.graph.delete_nodes(
            "FollowUp", database=SCOPE.database, where=lambda p: p.get("status") == "done"
        )
        self.graph.save()
        after = self.priya.observe(KG, thresholds=thresholds)
        self.drift = after.drift
        if after.drift is None:
            self.say("No Drift detected")
            return
        self.say(
            f"Drift event {after.drift.id[:8]} against {after.drift.contract_alias} -> "
            f"v{after.drift.ontology_version}:"
        )
        for f in after.drift.findings:
            self.say(
                f"  - {f.kind} {f.subject_kind} {f.subject}" + (f": {f.detail}" if f.detail else "")
            )

    def finish(self) -> None:
        here = EXAMPLE_DIR.resolve() == Path.cwd().resolve()
        production = self.priya.get_contract_version(KG).number
        self.say(
            "",
            f"production -> v{production}. The same verdicts in the web UI and in CI"
            + ("" if here else f" (from {EXAMPLE_DIR})")
            + ":",
            f"  {'uv run stetiq ui':<60}  # http://127.0.0.1:5000/ui",
            f"  {f'uv run stetiq gate {KG} --run <run id>':<60}  # the Gates of stetiq.yaml",
            f"  {f'uv run stetiq consumer gate {KG} --run <run id>':<60}  # every Consumer Gate",
        )


# --- output -------------------------------------------------------------------------


def _mark(passed: bool) -> str:
    return "✅" if passed else "❌"


def summary_line(r: RoundResult) -> str:
    """One PR-style line per round."""
    parts = [f"{ROUND_LABEL[r.round]:<11} Gate {_mark(r.gates.passed)}"]
    if r.consumer_gates:
        per_consumer = []
        for c in sorted(r.consumer_gates, key=lambda c: c.passed):  # failures first
            notes = [
                f"{f.competency_question} {f.before} → {f.after}, {_percent(f.change)}"
                for o in c.outcomes
                for f in o.findings
                if f.change is not None
            ] + [f"{q} new, not compared" for o in c.outcomes for q in o.new_questions]
            per_consumer.append(
                f"{c.consumer} {_mark(c.passed)}" + (f" {', '.join(notes)}" if notes else "")
            )
        parts.append(f"Consumer Gate {_mark(r.consumer_gates_passed)} ({'; '.join(per_consumer)})")
    if r.promoted:
        parts.append(f"promoted: production -> v{r.gates.ontology_version}")
    elif r.consumer_gates:
        parts.append(f"not promoted (Candidate stays at v{r.gates.ontology_version})")
    return "   ".join(parts)


def _percent(change: float | None) -> str:
    sign = "\N{MINUS SIGN}" if (change or 0) < 0 else "+"
    return "" if change is None else f"{sign}{abs(change) * 100:.0f}%"


def detail_lines(r: RoundResult) -> list[str]:
    lines = []
    for o in r.gates.outcomes:
        if not o.passed:
            lines.append(f"            Gate {o.gate.name} failed: {'; '.join(o.reasons[:3])}")
        elif o.gate.check == "ontology_diff" and o.reasons:
            lines.append(f"            Gate {o.gate.name}: {'; '.join(o.reasons)}")
    for c in r.consumer_gates:
        for o in c.outcomes:
            lines.append(
                f"            {c.consumer} {o.gate.name} {_mark(o.passed)}"
                + (f": {'; '.join(o.reasons)}" if o.reasons else "")
            )
    return lines


def _question_rows(client: stetiq.Client, run: stetiq.ConstructionRun) -> dict[str, int]:
    results = client.get_run_evaluation_results(run.id)
    execution = next(r for r in results if r.evaluator == "competency_question_execution")
    return {d.item: d.data["rows"] for d in execution.details if d.data}


def _coverage(client: stetiq.Client, run: stetiq.ConstructionRun) -> float:
    results = client.get_run_evaluation_results(run.id)
    return next(r for r in results if r.evaluator == "report_coverage").metrics["coverage"]


def eval_lines(
    client: stetiq.Client, before: stetiq.ConstructionRun, after: stetiq.ConstructionRun
) -> list[str]:
    """The evals the team watches, v1 -> prompt v2: report coverage and the rows each
    executed Competency Question returns."""
    rows_before, rows_after = _question_rows(client, before), _question_rows(client, after)
    changes = [
        f"{q} {rows_before.get(q, 0)} → {rows_after[q]}"
        for q in rows_after
        if rows_after[q] != rows_before.get(q, 0)
    ]
    return [
        f"            Evals v1 → prompt v2: report_coverage {_coverage(client, before):.2f} → "
        f"{_coverage(client, after):.2f}; rows: {', '.join(changes) or 'unchanged'}"
    ]


def run_demo(
    *,
    tracking_uri: str = DEFAULT_TRACKING_URI,
    graph_file: Path = DEFAULT_GRAPH_FILE,
    model: str = DEFAULT_MODEL,
    record: frozenset[Round] = frozenset(),
    live: bool = False,
    epilogue: bool = False,
    quiet: bool = False,
) -> Demo:
    demo = Demo(
        tracking_uri=tracking_uri,
        graph_file=graph_file,
        model=model,
        record=record,
        live=live,
        quiet=quiet,
    )
    demo.say(WITHOUT_STETIQ, "")
    demo.declare()
    demo.round_v1()
    demo.round_v2()
    demo.round_fix()
    if epilogue:
        demo.epilogue()
    demo.finish()
    return demo


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument(
        "--live",
        action="store_true",
        help="call the claude CLI for real, caching to the gitignored .graphdb/llm-cache/",
    )
    modes.add_argument(
        "--record",
        nargs="*",
        choices=ROUNDS,
        metavar="ROUND",
        help="call the claude CLI and overwrite the committed llm-cache/ entries of these "
        "rounds (default: all three)",
    )
    parser.add_argument("--epilogue", action="store_true", help="add the Drift beat")
    parser.add_argument(
        "--model", default=DEFAULT_MODEL, help=f"model for Claude (default {DEFAULT_MODEL})"
    )
    parser.add_argument("--tracking-uri", default=DEFAULT_TRACKING_URI)
    parser.add_argument("--graph-file", default=str(DEFAULT_GRAPH_FILE))
    parser.add_argument(
        "--reset",
        action="store_true",
        help="delete the tracking database and the graph store first",
    )
    args = parser.parse_args(argv)

    db = (
        Path(args.tracking_uri.removeprefix("sqlite:///"))
        if args.tracking_uri.startswith("sqlite:///")
        else None
    )
    graph_file = Path(args.graph_file)
    if args.reset:
        for path in (db, graph_file):
            if path is not None and path.exists():
                path.unlink()
    elif db is not None and db.exists():
        print(
            f"{db} already holds a previous run of the demo; pass --reset to start over",
            file=sys.stderr,
        )
        return 1
    if db is not None:
        db.parent.mkdir(parents=True, exist_ok=True)
    record: frozenset[Round] = (
        frozenset() if args.record is None else frozenset(args.record or ROUNDS)
    )
    try:
        run_demo(
            tracking_uri=args.tracking_uri,
            graph_file=graph_file,
            model=args.model,
            record=record,
            live=args.live,
            epilogue=args.epilogue,
        )
    except (stetiq.StetiqError, ExtractionError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
