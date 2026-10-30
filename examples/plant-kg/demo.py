"""Walk through stetiq on the plant maintenance Knowledge Graph.

    cd examples/plant-kg
    uv run python demo.py            # Claude extraction when the `claude` CLI is installed
    uv run python demo.py --extractor rules   # fully offline
    uv run stetiq ui                 # then browse the result

Everything is local: the tracking database is .stetiq/stetiq.db, the graph database
is the file .graphdb/plant.json (see graphdb.py). README.md tells the story.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

EXAMPLE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(EXAMPLE_DIR))

from evaluators import Documented, ReportCoverage  # noqa: E402
from graphdb import DEFAULT_DATABASE, LocalGraph  # noqa: E402
from pipeline import (  # noqa: E402
    DEFAULT_GRAPH_FILE,
    DEFAULT_LLM_CACHE,
    DEFAULT_MODEL,
    ClaudeExtractor,
    Extractor,
    RulesV1,
    build,
    make_extractor,
)

import stetiq  # noqa: E402
from stetiq import EntryPoint, GoldOntologyAlignment, GraphSourceScope  # noqa: E402
from stetiq.config import load_config  # noqa: E402
from stetiq.drift import thresholds_from_config  # noqa: E402

KG = "plant-maintenance"
GOLD_KG = "plant-gold"
SCOPE = GraphSourceScope(database=DEFAULT_DATABASE)
CONFIG = EXAMPLE_DIR / "stetiq.yaml"
ONTOLOGY = EXAMPLE_DIR / "ontology"
USE_CASE = EXAMPLE_DIR / "use-case.yaml"
DEFAULT_TRACKING_URI = f"sqlite:///{EXAMPLE_DIR / '.stetiq' / 'stetiq.db'}"

DESCRIPTION = """Maintenance history of the two production lines: **work orders** from the CMMS,
the **machines** and **lines** from the asset register, and what the technicians' free-text
reports add (components, root causes, follow-ups, part suppliers).

Built by `examples/plant-kg/pipeline.py`; the Competency Questions are the maintenance
lead's questions in `use-case.yaml`."""


class Demo:
    """The state the walkthrough builds up (the test reads it back)."""

    def __init__(
        self,
        *,
        tracking_uri: str,
        graph_file: Path,
        extractor: str,
        model: str,
        llm_cache: Path,
        quiet: bool,
    ) -> None:
        self.tracking_uri = tracking_uri
        self.graph = LocalGraph(graph_file)
        self.quiet = quiet
        self.extractor: Extractor = make_extractor(extractor, model=model, cache_dir=llm_cache)
        # Two users of the same tracking database: the maintenance engineer who builds the
        # graph, and the CI job that gates and promotes. The audit log names each one.
        self.priya = stetiq.Client(tracking_uri, graph_source=self.graph, actor="priya.natarajan")
        self.priya.register_evaluator(Documented())
        self.priya.register_evaluator(ReportCoverage())
        self.ci = stetiq.Client(tracking_uri, graph_source=self.graph, actor="ci-bot")
        # What `stetiq run` / run_entry_point hands the pipeline process, the way a real
        # pipeline gets its database credentials: from the environment, never from stetiq.
        os.environ["PLANT_GRAPH_FILE"] = str(graph_file)
        os.environ["PLANT_EXTRACTOR"] = self.extractor.name
        os.environ["PLANT_EXTRACTION_MODEL"] = model
        os.environ["PLANT_LLM_CACHE"] = str(llm_cache)
        # stetiq.yaml says `python`: make sure that is this interpreter.
        os.environ["PATH"] = (
            f"{Path(sys.executable).parent}{os.pathsep}{os.environ.get('PATH', '')}"
        )

    # --- output -----------------------------------------------------------------------

    def say(self, *lines: str) -> None:
        if not self.quiet:
            print(*lines, sep="\n", flush=True)

    def act(self, title: str) -> None:
        self.say("", f"=== {title} ", "")

    # --- 1. declare -------------------------------------------------------------------

    def declare(self) -> None:
        self.act("1. Declare: the Knowledge Graph, its Ontology and its Use Case")
        client = self.priya
        client.create_knowledge_graph(KG, ontology=ONTOLOGY / "initial.yaml")
        client.set_knowledge_graph_description(KG, DESCRIPTION)
        client.bind_graph_source(KG, SCOPE)
        client.create_knowledge_graph(GOLD_KG, ontology=ONTOLOGY / "gold.yaml")
        self.say(
            f"Created {KG} from ontology/initial.yaml (Ontology Version 1, production -> v1)",
            f"Bound it to the Graph Source scope database={SCOPE.database} of {self.graph.path}",
            f"Created {GOLD_KG} from ontology/gold.yaml, the architecture team's reference",
        )
        use_case = client.register_use_case(KG, USE_CASE)
        self.say(
            f"Registered the Use Case (Use Case Version {use_case.number}): "
            f"{len(use_case.use_case.competency_questions)} Competency Questions"
        )
        self.show_answerability(1)

    def show_answerability(self, version: int) -> None:
        result = _result(self.priya.get_evaluation_results(KG, version), "structural_answerability")
        m = result.metrics
        self.say(
            f"structural_answerability of v{version} against Use Case Version "
            f"{result.use_case_version}: {m['answerable_questions']}/{m['questions']} "
            f"answerable, {m['unanswerable_questions']} unanswerable, "
            f"{m['unmapped_questions']} unmapped (ratio {m['answerable_ratio']:.3f})"
        )
        for d in result.details:
            if d.data and d.data["status"] != "answerable":
                self.say(f"  - {d.item}: {d.message}")

    # --- 2. build ---------------------------------------------------------------------

    def first_run(self) -> None:
        self.act("2. Build: the first Construction Run, with the old regex pipeline")
        with self.priya.start_run(KG) as run:
            run.log_params(
                {
                    "extractor": "rules-v1",
                    "sources": "machines.csv, material_flow.json, work_orders.csv, reports/",
                }
            )
            stats = build(
                self.graph,
                ontology=run.declared_ontology,
                extractor=RulesV1(),
                database=SCOPE.database,
            )
            run.log_metrics(_metrics(stats))
        self.run1 = self.priya.get_run(run.id)
        self.say(
            f"Run {self.run1.id[:8]} declared v{self.run1.ontology_version}; "
            f"read {stats.reports_read}/{stats.reports} reports "
            f"(skipped: {', '.join(stats.skipped) or 'none'}); "
            f"wrote {stats.nodes} nodes and {stats.relationships} relationships"
        )
        self.show_run(self.run1)

    def show_run(self, run: stetiq.ConstructionRun) -> None:
        self.say(f"Status: {run.status}")
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
        if run.candidate_version:
            self.say(
                f"Evolution Mode evolving: registered Candidate Ontology Version {run.candidate_version} from what it observed"
            )
        results = self.priya.get_run_evaluation_results(run.id)
        execution = _result(results, "competency_question_execution")
        m = execution.metrics
        self.say(
            f"competency_question_execution: {m['passed_questions']}/{m['questions']} passed, "
            f"{m['skipped_questions']} skipped (no query); pass_ratio {m['pass_ratio']:.3f}"
        )
        for d in execution.details:
            if d.data and d.data["status"] != "passed":
                self.say(f"  - {d.item}: {d.message}")
        coverage = _result(results, "report_coverage").metrics
        self.say(
            f"report_coverage (custom run Evaluator): {coverage['coverage']:.3f} "
            f"({coverage['without_follow_ups']:.0f} of {coverage['work_orders']:.0f} work orders without a readable report)"
        )

    # --- 3. evaluate ------------------------------------------------------------------

    def evaluate_candidate(self) -> None:
        self.act("3. Evaluate: what do the Evaluators and the Gates say about the Candidate?")
        gold = self.priya.get_ontology_version(GOLD_KG, 1)
        results = self.priya.evaluate(KG, 2, evaluators=[GoldOntologyAlignment(gold)])
        self.show_version_evaluation(results)
        diff = self.priya.diff_ontology_versions(KG)  # contract (v1) -> latest Candidate (v2)
        self.say(f"Ontology Diff v1 -> v2: {diff.classification}")
        for c in diff.changes:
            self.say(f"  - {c.classification} {c.kind} {c.concept_kind} {c.concept}: {c.detail}")
        self.gates_candidate = self.ci.evaluate_gates(KG, CONFIG, version=2)
        self.show_gates(self.gates_candidate)

    def show_version_evaluation(self, results: list[stetiq.EvaluationResult]) -> None:
        by_name = {r.evaluator: r for r in results}
        wanted = {
            "hierarchy": ("max_depth",),
            "orphan_concepts": ("orphan_concepts",),
            "isolated_node_types": ("isolated_node_types",),
            "constraint_consistency": ("inconsistencies",),
            "redundancy": ("duplicate_structure_concepts",),
            "documented": ("undocumented",),
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

    def show_gates(self, result: stetiq.GateResult) -> None:
        self.say(
            f"Gates from stetiq.yaml on Ontology Version {result.ontology_version}: "
            f"{'all passed' if result.passed else f'{len(result.failed)} of {len(result.outcomes)} failed'}"
        )
        for o in result.outcomes:
            self.say(f"  {'PASS' if o.passed else 'FAIL'}  {o.gate.name}")
            for reason in o.reasons[:3]:
                self.say(f"        - {reason}")

    # --- 4. improve -------------------------------------------------------------------

    def improve(self) -> None:
        self.act("4. Improve: revise the Ontology, switch the extractor, gate and promote")
        v3 = self.priya.register_ontology(KG, ONTOLOGY / "revised.yaml")
        diff = self.priya.diff_ontology_versions(KG, 1, v3.number)
        self.say(
            f"Registered ontology/revised.yaml as v{v3.number}; diff v1 -> v{v3.number} is "
            f"{diff.classification} ({len(diff.changes)} changes)"
        )
        use_case = self.priya.add_competency_question(
            KG,
            {
                "id": "parts-suppliers",
                "question": "Which suppliers do we depend on for replacement parts?",
                "query": "MATCH (c:Component)-[:SUPPLIED_BY]->(s:Supplier) RETURN c.name AS component, s.name AS supplier",
            },
        )
        self.say(
            f"Added the Competency Question parts-suppliers: Use Case Version {use_case.number}"
        )
        self.show_answerability(v3.number)

        self.say(
            "",
            f"Second Construction Run against v{v3.number} with the {self.extractor.name} extractor"
            + (f" ({self.extractor.model})" if isinstance(self.extractor, ClaudeExtractor) else ""),
        )
        with self.priya.start_run(KG, ontology_version=v3.number) as run:
            run.log_params(
                {
                    "extractor": self.extractor.name,
                    "sources": "machines.csv, material_flow.json, work_orders.csv, technicians.csv, reports/",
                }
            )
            if isinstance(self.extractor, ClaudeExtractor):
                run.log_param("model", self.extractor.model)
            stats = build(
                self.graph,
                ontology=run.declared_ontology,
                extractor=self.extractor,
                database=SCOPE.database,
            )
            run.log_metrics(_metrics(stats))
        self.run2 = self.priya.get_run(run.id)
        self.show_run(self.run2)

        self.say(
            "",
            "Nightly rebuild through the Construction Entry Point of stetiq.yaml (what `stetiq run` does)",
        )
        entry_point = EntryPoint.from_config(load_config(CONFIG))
        self.nightly = self.priya.run_entry_point(
            KG, entry_point, ontology_version=v3.number, cwd=EXAMPLE_DIR
        )
        self.say(
            f"Run {self.nightly.id[:8]}: {self.nightly.status}, Conformance "
            f"{self.nightly.conformance.score:.3f}"
            if self.nightly.conformance
            else f"Run {self.nightly.id[:8]}: {self.nightly.status}"
        )

        comparison = self.priya.compare_runs([self.run1.id, self.run2.id, self.nightly.id])
        self.say("", "compare_runs: run 1 | run 2 | nightly")
        self.say(f"  Ontology Version: {' | '.join(f'v{n}' for n in comparison.ontology_versions)}")
        for key, values in comparison.params.items():
            self.say(f"  param {key}: {' | '.join(str(v) for v in values)}")
        for key, values in comparison.metrics.items():
            self.say(
                f"  metric {key}: {' | '.join(f'{v:g}' if v is not None else '-' for v in values)}"
            )
        self.say(
            f"  Conformance: {' | '.join(f'{c.score:.3f}' if c else '-' for c in comparison.conformance)}"
        )
        for key in ("competency_question_execution.pass_ratio", "report_coverage.coverage"):
            values = comparison.evaluations.get(key, ())
            self.say(f"  {key}: {' | '.join(f'{v:.3f}' if v is not None else '-' for v in values)}")

        self.say("", f"Evaluators on v{v3.number} (gold_alignment against {GOLD_KG} v1):")
        gold = self.priya.get_ontology_version(GOLD_KG, 1)
        self.show_version_evaluation(
            self.priya.evaluate(KG, v3.number, evaluators=[GoldOntologyAlignment(gold)])
        )

        self.gates_revised = self.ci.evaluate_gates(KG, CONFIG, version=v3.number)
        self.show_gates(self.gates_revised)
        if self.gates_revised.passed:
            self.priya.set_alias(KG, "staging", v3.number)
            self.ci.set_alias(KG, "production", v3.number)
            self.say(
                f"Promoted: staging -> v{v3.number} (priya), production -> v{v3.number} (ci-bot)"
            )
        else:
            self.say("Gates failed: not promoting. Fix the Ontology or the pipeline and run again.")
        self.say("Promotion audit log:")
        for p in self.priya.list_promotions(KG):
            self.say(
                f"  {p.promoted_at:%Y-%m-%d %H:%M} {p.alias}: v{p.from_version or '-'} -> v{p.to_version} by {p.actor}, Gate result {p.gate_result or '-'}"
            )

    # --- 5. operate -------------------------------------------------------------------

    def operate(self) -> None:
        self.act("5. Operate: Observations and Drift, strict Evolution Mode, a breaking proposal")
        thresholds = thresholds_from_config(load_config(CONFIG))
        before = self.priya.observe(KG, thresholds=thresholds)
        self.say(
            f"Observation {before.observation.id[:8]} outside any run: "
            f"{'Drift' if before.drifted else 'no Drift'} against the Contract Alias's version"
        )

        self.say(
            "",
            "Someone runs a fix script directly against the database: adds SparePart nodes, deletes the done follow-ups",
        )
        for sku in ("SKF-6205", "PKR-H2-500", "FST-VUVG-L10"):
            self.graph.add_node(["SparePart"], {"sku": sku}, database=SCOPE.database)
        deleted = self.graph.delete_nodes(
            "FollowUp", database=SCOPE.database, where=lambda p: p.get("status") == "done"
        )
        self.graph.save()
        self.say(f"  ({deleted} FollowUp nodes deleted)")
        after = self.priya.observe(KG, thresholds=thresholds)
        self.drift = after.drift
        if after.drift is None:
            self.say("No Drift detected")
        else:
            self.say(
                f"Drift event {after.drift.id[:8]} against {after.drift.contract_alias} -> v{after.drift.ontology_version}, "
                f"thresholds max_count_drop={thresholds.max_count_drop}:"
            )
            for f in after.drift.findings:
                self.say(
                    f"  - {f.kind} {f.subject_kind} {f.subject}"
                    + (f": {f.detail}" if f.detail else "")
                )

        self.say(
            "",
            "Strict Evolution Mode: the pipeline is run with the experimental Sensor nodes switched on",
        )
        self.priya.set_evolution_mode(KG, "strict")
        with self.priya.start_run(KG) as run:
            run.log_params({"extractor": self.extractor.name, "sensors": True})
            build(
                self.graph,
                ontology=run.declared_ontology,
                extractor=self.extractor,
                database=SCOPE.database,
                sensors=True,
            )
        self.strict_run = self.priya.get_run(run.id)
        undeclared = [
            m.subject
            for m in (self.strict_run.conformance.mismatches if self.strict_run.conformance else ())
            if m.kind == "undeclared"
        ]
        self.say(
            f"Run {self.strict_run.id[:8]}: {self.strict_run.status}, Candidate: {self.strict_run.candidate_version}; "
            f"undeclared: {', '.join(undeclared)}"
        )
        self.priya.set_evolution_mode(KG, "evolving")

        self.say("", "A pull request proposes ontology/proposal-rename-work-order.yaml")
        proposal = self.priya.register_ontology(KG, ONTOLOGY / "proposal-rename-work-order.yaml")
        self.gates_proposal = self.ci.evaluate_gates(KG, CONFIG, version=proposal.number)
        self.show_gates(self.gates_proposal)

    # --- 6. finish --------------------------------------------------------------------

    def finish(self) -> None:
        self.act("6. Browse")
        versions = self.priya.list_ontology_versions(KG)
        self.say(
            f"{KG}: Ontology Versions "
            + ", ".join(f"v{v.number} ({v.origin})" for v in versions)
            + f"; production -> v{self.priya.get_contract_version(KG).number}"
        )
        if isinstance(self.extractor, ClaudeExtractor):
            self.say(
                f"Claude Code CLI calls: {self.extractor.calls} ({self.extractor.cache_hits} served from the cache in {self.extractor.cache_dir})"
            )
        here = EXAMPLE_DIR.resolve() == Path.cwd().resolve()
        self.say(
            "",
            "Open the web UI and the CLI on this tracking database"
            + ("" if here else f" (from {EXAMPLE_DIR})")
            + ":",
            "  uv run stetiq ui                      # http://127.0.0.1:5000/ui",
            f"  uv run stetiq runs list {KG}",
            f"  uv run stetiq gate {KG} --run {self.nightly.id}   # the nightly run passed every Gate",
            f"  uv run stetiq gate-results {KG}       # every recorded Gate evaluation",
            f"  uv run stetiq ontology diff {KG} 1 3",
            f"  uv run stetiq alias log {KG}",
            f"  uv run stetiq drift list {KG}",
        )


def _result(results: list[stetiq.EvaluationResult], evaluator: str) -> stetiq.EvaluationResult:
    return next(r for r in results if r.evaluator == evaluator)


def _metrics(stats) -> dict[str, float]:
    return {
        "reports": stats.reports,
        "reports_read": stats.reports_read,
        "nodes": stats.nodes,
        "relationships": stats.relationships,
    }


def run_demo(
    *,
    tracking_uri: str = DEFAULT_TRACKING_URI,
    graph_file: Path = DEFAULT_GRAPH_FILE,
    extractor: str = "auto",
    model: str = DEFAULT_MODEL,
    llm_cache: Path = DEFAULT_LLM_CACHE,
    quiet: bool = False,
) -> Demo:
    if extractor == "rules":
        extractor = "rules-v2"
    demo = Demo(
        tracking_uri=tracking_uri,
        graph_file=graph_file,
        extractor=extractor,
        model=model,
        llm_cache=llm_cache,
        quiet=quiet,
    )
    demo.say(
        f"stetiq {demo.tracking_uri}; graph store {demo.graph.path}; extractor for runs 2+: {demo.extractor.name}"
    )
    demo.declare()
    demo.first_run()
    demo.evaluate_candidate()
    demo.improve()
    demo.operate()
    demo.finish()
    return demo


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--extractor",
        default="auto",
        choices=["auto", "rules", "claude"],
        help="who reads the technicians' reports from the second run on (default: claude if installed, else rules)",
    )
    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        help=f"model for the claude extractor (default {DEFAULT_MODEL})",
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
            f"{db} already holds a previous walkthrough; pass --reset to start over",
            file=sys.stderr,
        )
        return 1
    if db is not None:
        db.parent.mkdir(parents=True, exist_ok=True)
    try:
        run_demo(
            tracking_uri=args.tracking_uri,
            graph_file=graph_file,
            extractor=args.extractor,
            model=args.model,
        )
    except stetiq.StetiqError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
