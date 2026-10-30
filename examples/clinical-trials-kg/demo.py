"""Walk through stetiq on the hospital's clinical-trials registry Knowledge Graph.

    cd examples/clinical-trials-kg
    uv run python demo.py            # fully offline and deterministic
    uv run stetiq ui                 # then browse the result

Everything is local: the tracking database is .stetiq/stetiq.db, the graph database
is the file .graphdb/registry.json (see trials_graph.py). README.md tells the story.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

EXAMPLE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(EXAMPLE_DIR))
try:
    from trials_evaluators import ConsentCoverage, PiiFree
    from trials_graph import DEFAULT_DATABASE, RegistryGraph
    from trials_pipeline import DEFAULT_GRAPH_FILE, load
finally:
    sys.path.remove(str(EXAMPLE_DIR))

import stetiq  # noqa: E402
from stetiq import EntryPoint, GoldOntologyAlignment, GraphSourceScope  # noqa: E402
from stetiq.config import load_config  # noqa: E402
from stetiq.drift import thresholds_from_config  # noqa: E402

KG = "trial-registry"
GOLD_KG = "trial-registry-gold"
SCOPE = GraphSourceScope(database=DEFAULT_DATABASE)
CONFIG = EXAMPLE_DIR / "stetiq.yaml"
ONTOLOGY = EXAMPLE_DIR / "ontology"
USE_CASE = EXAMPLE_DIR / "use-case.yaml"
MAY_EXPORT = "export-2026-05"
JUNE_EXPORT = "export-2026-06"
DEFAULT_TRACKING_URI = f"sqlite:///{EXAMPLE_DIR / '.stetiq' / 'stetiq.db'}"

DESCRIPTION = """The hospital's clinical-trials registry: **trials**, their **sites** and
**investigators**, the **interventions** under test (drugs, devices, procedures), the
**conditions** studied, and per pseudonymous **participant** the consent, the arm, the
**visits** and the **adverse events**.

A regulated registry, run in strict Evolution Mode from day one: nothing enters the graph
that the Ontology did not declare. Built by `examples/clinical-trials-kg/trials_pipeline.py`
from the monthly registry export; the Competency Questions in `use-case.yaml` are the
safety monitor's."""


class Demo:
    """The state the walkthrough builds up (the test reads it back)."""

    def __init__(self, *, tracking_uri: str, graph_file: Path, quiet: bool) -> None:
        self.tracking_uri = tracking_uri
        self.graph = RegistryGraph(graph_file)
        self.quiet = quiet
        # Two users of the same tracking database: the clinical data manager who owns the
        # Ontology and loads the exports, and the clinical data management bot that gates
        # and moves production. The audit log names each one.
        self.dana = stetiq.Client(tracking_uri, graph_source=self.graph, actor="dana.reyes")
        self.dana.register_evaluator(PiiFree())
        self.dana.register_evaluator(ConsentCoverage())
        self.bot = stetiq.Client(tracking_uri, graph_source=self.graph, actor="cdm-bot")
        # What run_entry_point hands the loader process, the way a real loader gets its
        # database credentials: from the environment, never from stetiq.
        os.environ["TRIALS_GRAPH_FILE"] = str(graph_file)
        os.environ["TRIALS_EXPORT"] = MAY_EXPORT
        os.environ.pop("TRIALS_BIOMARKERS", None)
        # stetiq.yaml says `python`: make sure that is this interpreter.
        os.environ["PATH"] = (
            f"{Path(sys.executable).parent}{os.pathsep}{os.environ.get('PATH', '')}"
        )
        self.entry_point = EntryPoint.from_config(load_config(CONFIG))

    # --- output -----------------------------------------------------------------------

    def say(self, *lines: str) -> None:
        if not self.quiet:
            print(*lines, sep="\n", flush=True)

    def act(self, title: str) -> None:
        self.say("", f"=== {title} ", "")

    # --- 1. declare -------------------------------------------------------------------

    def declare(self) -> None:
        self.act("1. Declare: the Knowledge Graph, strict from day one, and the Use Case")
        client = self.dana
        client.create_knowledge_graph(KG, ontology=ONTOLOGY / "v1.yaml")
        client.set_knowledge_graph_description(KG, DESCRIPTION)
        client.bind_graph_source(KG, SCOPE)
        client.set_evolution_mode(KG, "strict")
        client.create_knowledge_graph(GOLD_KG, ontology=ONTOLOGY / "gold.yaml")
        self.say(
            f"Created {KG} from ontology/v1.yaml (Ontology Version 1, production -> v1)",
            f"Bound it to the Graph Source scope database={SCOPE.database} of {self.graph.path}",
            f"Evolution Mode: {client.get_evolution_mode(KG)}. A run that introduces an undeclared "
            "Concept fails; it never yields a Candidate.",
            f"Created {GOLD_KG} from ontology/gold.yaml, the data standards team's reference",
        )
        use_case = client.register_use_case(KG, USE_CASE)
        self.say(
            f"Registered the Use Case (Use Case Version {use_case.number}): "
            f"{len(use_case.use_case.competency_questions)} Competency Questions"
        )
        self.show_answerability(1)

    def show_answerability(self, version: int) -> None:
        result = _result(self.dana.get_evaluation_results(KG, version), "structural_answerability")
        m = result.metrics
        self.say(
            f"structural_answerability of v{version}: {m['answerable_questions']}/{m['questions']} "
            f"answerable, {m['unanswerable_questions']} unanswerable, "
            f"{m['unmapped_questions']} unmapped (ratio {m['answerable_ratio']:.3f})"
        )
        for d in result.details:
            if d.data and d.data["status"] != "answerable":
                self.say(f"  - {d.item}: {d.message}")

    # --- 2. build ---------------------------------------------------------------------

    def first_runs(self) -> None:
        self.act("2. Build: the May export meets the strict contract")
        self.say(f"First Construction Run: the loader writes every column of {MAY_EXPORT}")
        with self.dana.start_run(KG) as run:
            run.log_params({"export": MAY_EXPORT, "loader": "trials_pipeline.load"})
            stats = load(self.graph, ontology=run.declared_ontology, export=MAY_EXPORT)
            run.log_metrics({"nodes": stats.nodes, "relationships": stats.relationships})
        self.run1 = self.dana.get_run(run.id)
        self.say(
            f"Run {self.run1.id[:8]} declared v{self.run1.ontology_version}; wrote "
            f"{stats.nodes} nodes and {stats.relationships} relationships"
        )
        self.show_run(self.run1)
        self.say(
            f"production still -> v{self.dana.get_contract_version(KG).number}; "
            f"Ontology Versions: {[v.number for v in self.dana.list_ontology_versions(KG)]}. "
            "The contract held: the undeclared Concepts stayed out of the Ontology.",
            "",
            "Governance: the data manager reviews the export, finds the arm column and the",
            "participant-event link legitimate, and declares them in ontology/v2.yaml",
        )
        v2 = self.dana.register_ontology(KG, ONTOLOGY / "v2.yaml")
        diff = self.dana.diff_ontology_versions(KG, 1, v2.number)
        self.say(
            f"Registered ontology/v2.yaml as v{v2.number} (origin {v2.origin}); "
            f"diff v1 -> v{v2.number} is {diff.classification} ({len(diff.changes)} changes)"
        )
        for c in diff.changes:
            if c.kind == "added":
                self.say(f"  - {c.classification} {c.kind} {c.concept_kind} {c.concept}")
        self.show_answerability(v2.number)
        self.say("", f"Second Construction Run, against v{v2.number}, same export")
        with self.dana.start_run(KG, ontology_version=v2.number) as run:
            run.log_params({"export": MAY_EXPORT, "loader": "trials_pipeline.load"})
            stats = load(self.graph, ontology=run.declared_ontology, export=MAY_EXPORT)
            run.log_metrics({"nodes": stats.nodes, "relationships": stats.relationships})
        self.run2 = self.dana.get_run(run.id)
        self.show_run(self.run2)

    def show_run(self, run: stetiq.ConstructionRun) -> None:
        self.say(f"Status: {run.status}; Candidate: {run.candidate_version}")
        if run.conformance is None:
            return
        self.say(
            f"Conformance {run.conformance.score:.3f} with {len(run.conformance.mismatches)} mismatches"
            + (":" if run.conformance.mismatches else "")
        )
        for m in run.conformance.mismatches:
            self.say(
                f"  - {m.kind} {m.subject_kind} {m.subject}" + (f": {m.detail}" if m.detail else "")
            )
        if run.status == "failed":
            self.say("Evolution Mode strict: the run failed instead of yielding a Candidate")
        results = self.dana.get_run_evaluation_results(run.id)
        execution = _result(results, "competency_question_execution")
        m = execution.metrics
        self.say(
            f"competency_question_execution: {m['passed_questions']}/{m['questions']} passed, "
            f"{m['skipped_questions']} skipped (no query); pass_ratio {m['pass_ratio']:.3f}"
        )
        for d in execution.details:
            if d.data and d.data["status"] != "passed":
                self.say(f"  - {d.item}: {d.message}")
        coverage = _result(results, "consent_coverage").metrics
        self.say(
            f"consent_coverage (custom run Evaluator): {coverage['coverage']:.3f} "
            f"({coverage['without_consent']:.0f} of {coverage['participants']:.0f} participants "
            "without a CONSENTED_TO relationship)"
        )

    # --- 3. evaluate ------------------------------------------------------------------

    def evaluate_v2(self) -> None:
        self.act("3. Evaluate: v2 against the gold reference, the constraints and the Gates")
        gold = self.dana.get_ontology_version(GOLD_KG, 1)
        results = self.dana.evaluate(KG, 2, evaluators=[GoldOntologyAlignment(gold)])
        self.show_version_evaluation(results)
        self.gates_v2 = self.bot.evaluate_gates(KG, CONFIG, version=2)
        self.show_gates(self.gates_v2)

    def show_version_evaluation(self, results: list[stetiq.EvaluationResult]) -> None:
        by_name = {r.evaluator: r for r in results}
        wanted = {
            "hierarchy": ("max_depth", "root_node_types"),
            "orphan_concepts": ("orphan_concepts",),
            "constraint_consistency": ("inconsistencies",),
            "pii_free": ("pii_properties",),
            "structural_answerability": ("answerable_ratio",),
            "gold_alignment": ("precision", "recall"),
        }
        for name, metrics in wanted.items():
            r = by_name.get(name)
            if r is None:
                continue
            values = ", ".join(f"{k}={r.metrics[k]:.3g}" for k in metrics)
            items = ", ".join(d.item for d in r.details if d.metric in metrics)
            self.say(f"  {name}: {values}" + (f"  [{items}]" if items else ""))
        gold = by_name.get("gold_alignment")
        if gold is not None:
            missing = [d.item for d in gold.details if d.metric == "unmatched_reference_concepts"]
            self.say(f"  gold Concepts missing: {', '.join(missing)}")

    def show_gates(self, result: stetiq.GateResult) -> None:
        self.say(
            f"Gates from stetiq.yaml on Ontology Version {result.ontology_version}: "
            f"{'all passed' if result.passed else f'{len(result.failed)} of {len(result.outcomes)} failed'}"
        )
        for o in result.outcomes:
            self.say(f"  {'PASS' if o.passed else 'FAIL'}  {o.gate.name}")
            for reason in o.reasons[:3]:
                self.say(f"        - {reason}")

    # --- 4. align and correct ---------------------------------------------------------

    def align(self) -> None:
        self.act("4. Align: v3, the corrected June export, every Gate, then production")
        v3 = self.dana.register_ontology(KG, ONTOLOGY / "v3.yaml")
        diff = self.dana.diff_ontology_versions(KG, 1, v3.number)
        self.say(
            f"Registered ontology/v3.yaml as v{v3.number}; diff v1 -> v{v3.number} is "
            f"{diff.classification} ({len(diff.changes)} changes)"
        )
        os.environ["TRIALS_EXPORT"] = JUNE_EXPORT
        self.say(
            "",
            f"Third Construction Run through the Construction Entry Point of stetiq.yaml "
            f"(what `stetiq run` does), TRIALS_EXPORT={JUNE_EXPORT}",
        )
        self.run3 = self.dana.run_entry_point(
            KG, self.entry_point, ontology_version=v3.number, cwd=EXAMPLE_DIR
        )
        self.say(f"Run {self.run3.id[:8]} exit code {self.run3.params['entry_point.exit_code']}")
        self.show_run(self.run3)

        comparison = self.dana.compare_runs([self.run1.id, self.run2.id, self.run3.id])
        self.say("", "compare_runs: run 1 | run 2 | run 3")
        self.say(f"  Ontology Version: {' | '.join(f'v{n}' for n in comparison.ontology_versions)}")
        self.say(f"  status: {' | '.join(r.status for r in comparison.runs)}")
        for key, values in comparison.params.items():
            self.say(
                f"  param {key}: {' | '.join(str(v) if v is not None else '-' for v in values)}"
            )
        self.say(
            f"  Conformance: {' | '.join(f'{c.score:.3f}' if c else '-' for c in comparison.conformance)}"
        )
        for key in ("competency_question_execution.pass_ratio", "consent_coverage.coverage"):
            values = comparison.evaluations.get(key, ())
            self.say(f"  {key}: {' | '.join(f'{v:.3f}' if v is not None else '-' for v in values)}")

        self.say("", f"Evaluators on v{v3.number} (gold_alignment against {GOLD_KG} v1):")
        gold = self.dana.get_ontology_version(GOLD_KG, 1)
        self.show_version_evaluation(
            self.dana.evaluate(KG, v3.number, evaluators=[GoldOntologyAlignment(gold)])
        )
        self.gates_v3 = self.bot.evaluate_gates(KG, CONFIG, version=v3.number)
        self.show_gates(self.gates_v3)
        if self.gates_v3.passed:
            self.dana.set_alias(KG, "staging", v3.number)
            self.bot.set_alias(KG, "production", v3.number)
            self.say(
                f"Promoted: staging -> v{v3.number} (dana.reyes), production -> v{v3.number} (cdm-bot)"
            )
        else:
            self.say("Gates failed: the bot does not move production.")
        self.say("Promotion audit log:")
        for p in self.dana.list_promotions(KG):
            self.say(
                f"  {p.promoted_at:%Y-%m-%d %H:%M} {p.alias}: v{p.from_version or '-'} -> v{p.to_version} by {p.actor}, Gate result {p.gate_result or '-'}"
            )

    # --- 5. operate -------------------------------------------------------------------

    def operate(self) -> None:
        self.act("5. Operate: an Observation, an undeclared Biomarker, a breaking proposal")
        thresholds = thresholds_from_config(load_config(CONFIG))
        outcome = self.dana.observe(KG, thresholds=thresholds)
        self.drift = outcome.drift
        self.say(
            f"Observation {outcome.observation.id[:8]} between runs, on the untouched graph: "
            f"{'Drift' if outcome.drifted else 'no Drift'} against the Contract Alias's version"
        )

        self.say(
            "",
            "The lab switches on its experimental Biomarker feed (TRIALS_BIOMARKERS=1) and the",
            "nightly load runs against production (v3) in strict Evolution Mode",
        )
        os.environ["TRIALS_BIOMARKERS"] = "1"
        try:
            self.biomarker_run = self.dana.run_entry_point(KG, self.entry_point, cwd=EXAMPLE_DIR)
        finally:
            del os.environ["TRIALS_BIOMARKERS"]
        undeclared = [
            m.subject
            for m in (
                self.biomarker_run.conformance.mismatches if self.biomarker_run.conformance else ()
            )
            if m.kind == "undeclared"
        ]
        self.say(
            f"Run {self.biomarker_run.id[:8]}: {self.biomarker_run.status}, "
            f"Candidate: {self.biomarker_run.candidate_version}; undeclared: {', '.join(undeclared)}",
            f"production still -> v{self.dana.get_contract_version(KG).number}",
        )

        self.say("", "A pull request proposes ontology/proposal-merge-sites.yaml")
        proposal = self.dana.register_ontology(KG, ONTOLOGY / "proposal-merge-sites.yaml")
        self.gates_proposal = self.bot.evaluate_gates(KG, CONFIG, version=proposal.number)
        self.show_gates(self.gates_proposal)
        self.say(f"production still -> v{self.dana.get_contract_version(KG).number}")

    # --- 6. finish --------------------------------------------------------------------

    def finish(self) -> None:
        self.act("6. Browse")
        versions = self.dana.list_ontology_versions(KG)
        self.say(
            f"{KG}: Ontology Versions "
            + ", ".join(f"v{v.number} ({v.origin})" for v in versions)
            + f"; production -> v{self.dana.get_contract_version(KG).number}; "
            f"Evolution Mode {self.dana.get_evolution_mode(KG)}"
        )
        here = EXAMPLE_DIR.resolve() == Path.cwd().resolve()
        self.say(
            "",
            "Open the web UI and the CLI on this tracking database"
            + ("" if here else f" (from {EXAMPLE_DIR})")
            + ":",
            "  uv run stetiq ui                      # http://127.0.0.1:5000/ui",
            f"  uv run stetiq runs list {KG}",
            f"  uv run stetiq gate {KG} --run {self.run3.id}   # the June run passed every Gate",
            f"  uv run stetiq gate-results {KG}       # every recorded Gate evaluation",
            f"  uv run stetiq ontology diff {KG} 1 3",
            f"  uv run stetiq alias log {KG}",
            f"  uv run stetiq ontology list {KG}   # v1 to v4, every one registered by a human",
        )


def _result(results: list[stetiq.EvaluationResult], evaluator: str) -> stetiq.EvaluationResult:
    return next(r for r in results if r.evaluator == evaluator)


def run_demo(
    *,
    tracking_uri: str = DEFAULT_TRACKING_URI,
    graph_file: Path = DEFAULT_GRAPH_FILE,
    quiet: bool = False,
) -> Demo:
    demo = Demo(tracking_uri=tracking_uri, graph_file=graph_file, quiet=quiet)
    demo.say(f"stetiq {demo.tracking_uri}; graph database file {demo.graph.path}")
    demo.declare()
    demo.first_runs()
    demo.evaluate_v2()
    demo.align()
    demo.operate()
    demo.finish()
    return demo


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--tracking-uri", default=DEFAULT_TRACKING_URI)
    parser.add_argument("--graph-file", default=str(DEFAULT_GRAPH_FILE))
    parser.add_argument(
        "--reset",
        action="store_true",
        help="delete the tracking database and the graph database file first",
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
            f"{db} already holds a previous walkthrough; pass --reset to start over",
            file=sys.stderr,
        )
        return 1
    if db is not None:
        db.parent.mkdir(parents=True, exist_ok=True)
    try:
        run_demo(tracking_uri=args.tracking_uri, graph_file=graph_file)
    except stetiq.StetiqError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
