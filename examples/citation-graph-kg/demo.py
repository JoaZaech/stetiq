"""Walk through stetiq in server mode on the university's research-output Knowledge Graph.

    cd examples/citation-graph-kg
    uv run python demo.py                                   # starts an in-process server
    uv run stetiq ui --tracking-uri sqlite:///.stetiq/server.db   # then browse the result

Everything is local and offline: the stetiq server runs inside this process (FastAPI's
TestClient), its database is .stetiq/server.db, and the graph database is the file
.graphdb/scholar.json (see scholar_graph.py). Every call still goes over HTTP with an
API Token, exactly as it would against `stetiq server`. README.md tells the story.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

EXAMPLE_DIR = Path(__file__).resolve().parent
if str(EXAMPLE_DIR) not in sys.path:
    sys.path.insert(0, str(EXAMPLE_DIR))

from fastapi.testclient import TestClient  # noqa: E402
from scholar_evaluators import AuthorDedupe  # noqa: E402
from scholar_graph import DEFAULT_DATABASE, ScholarGraph  # noqa: E402
from scholar_pipeline import DEFAULT_GRAPH_FILE, build  # noqa: E402

import stetiq  # noqa: E402
from stetiq import EntryPoint, GraphSourceScope  # noqa: E402
from stetiq.auth import TokenRegistry  # noqa: E402
from stetiq.config import load_config  # noqa: E402
from stetiq.server import create_app  # noqa: E402
from stetiq.tracking import RemoteTrackingService  # noqa: E402

KG = "scholar-kg"
OTHER_KG = "campus-events-kg"  # a Knowledge Graph the fourth token may edit; scholar-kg is not
SCOPE = GraphSourceScope(database=DEFAULT_DATABASE)
CONFIG = EXAMPLE_DIR / "stetiq.yaml"
ONTOLOGY = EXAMPLE_DIR / "ontology"
USE_CASE = EXAMPLE_DIR / "use-case.yaml"
DEFAULT_TRACKING_URI = f"sqlite:///{EXAMPLE_DIR / '.stetiq' / 'server.db'}"
UNKNOWN_RUN_ID = "0" * 32

DESCRIPTION = """The university's research output: **papers**, their **authors**, the **venues** they
appeared in, the **grants** they acknowledge and the **citations** between them.

Built by `examples/citation-graph-kg/scholar_pipeline.py` from the publication database and
the ORCID sync; the Competency Questions are the research office's questions in `use-case.yaml`."""

SELF_CITATION_QUESTION = {
    "id": "self-citation-share",
    "question": "What share of our citations are self-citations, with authors identified by ORCID?",
    "query": (
        "MATCH (p:Paper)-[:CITES]->(q:Paper) "
        "WITH p, q, exists { MATCH (a:Author)-[:AUTHORED]->(p) WHERE a.orcid IS NOT NULL "
        "AND (a)-[:AUTHORED]->(q) } AS self_citation "
        "RETURN count(*) AS citations, sum(CASE WHEN self_citation THEN 1 ELSE 0 END) AS self_citations"
    ),
}
ORCID_COAUTHORS_QUESTION = {
    "id": "orcid-coauthors",
    "question": "Which ORCID-verified authors have co-authored with each other?",
    "query": (
        "MATCH (a:Author)-[:CO_AUTHORED]->(b:Author) "
        "WHERE a.orcid IS NOT NULL AND b.orcid IS NOT NULL "
        "RETURN a.name AS author, b.name AS co_author ORDER BY author, co_author"
    ),
}


class Demo:
    """The state the walkthrough builds up (the test reads it back)."""

    def __init__(
        self, *, database_url: str, http: TestClient, graph_file: Path, quiet: bool
    ) -> None:
        self.database_url = database_url
        self.http = http
        self.base_url = str(http.base_url)
        self.graph = ScholarGraph(graph_file)
        self.quiet = quiet
        # Tokens are issued against the server's database, never over HTTP
        # (what `stetiq token create` does).
        self.tokens = TokenRegistry(database_url)
        self.token_ids: dict[str, str] = {}
        # (Ontology Version, Use Case Version, answerable, questions), in story order.
        self.answerability: list[tuple[int, int, int, int]] = []
        # What the Construction Entry Point process gets from the environment, the way a
        # real loader gets its database credentials: never from stetiq.
        os.environ["SCHOLAR_GRAPH_FILE"] = str(graph_file)
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

    # --- 1. server and tokens ---------------------------------------------------------

    def client(
        self, user: str, grants: dict[str, str], *, actor: str | None = None
    ) -> stetiq.Client:
        """A Client for `user`, talking to the in-process server with a fresh API Token."""
        token, value = self.tokens.issue(user, grants)
        self.token_ids[user] = token.id
        self.say(
            f"  stetiq token create {user} "
            + " ".join(f"--grant {kg}={p}" for kg, p in grants.items())
            + f"   -> token {token.id}"
        )
        return stetiq.Client(
            self.base_url,
            service=RemoteTrackingService(self.base_url, http=self.http, token=value),
            graph_source=self.graph,
            actor=actor,
        )

    def tokens_and_clients(self) -> None:
        self.act("1. Server: one stetiq server, four API Tokens, three teams")
        self.say(f"Server {self.base_url} over {self.database_url}; graph file {self.graph.path}")
        self.office = self.client("research-office", {KG: "edit"})
        self.library = self.client("library", {KG: "read"})
        # The CI bot's Client is built with a wrong actor on purpose: the server records
        # the token's user, not what the client claims.
        self.ci = self.client("ci-bot", {KG: "edit"}, actor="someone-else")
        self.outsider = self.client("events-team", {OTHER_KG: "edit"})
        # Custom Evaluators live in the SDK process, per Client: both Clients that end
        # Construction Runs need the one the Gates name.
        self.office.register_evaluator(AuthorDedupe())
        self.ci.register_evaluator(AuthorDedupe())

    # --- 2. declare -------------------------------------------------------------------

    def declare(self) -> None:
        self.act("2. Declare: the research office registers the Ontology and the Use Case")
        self.office.create_knowledge_graph(KG, ontology=ONTOLOGY / "v1.yaml")
        self.office.set_knowledge_graph_description(KG, DESCRIPTION)
        self.office.bind_graph_source(KG, SCOPE)
        use_case = self.office.register_use_case(KG, USE_CASE)
        self.say(
            f"Created {KG} from ontology/v1.yaml (Ontology Version 1, production -> v1)",
            f"Bound it to the Graph Source scope database={SCOPE.database}",
            f"Registered the Use Case (Use Case Version {use_case.number}): "
            f"{len(use_case.use_case.competency_questions)} Competency Questions",
        )
        self.show_answerability(1)

        self.say("", "The library's token reads, and only reads:")
        versions = self.library.list_ontology_versions(KG)
        self.say(f"  list_ontology_versions -> {[v.number for v in versions]}")
        try:
            self.library.register_ontology(KG, ONTOLOGY / "v3.yaml")
        except stetiq.PermissionDeniedError as e:
            self.library_denied = str(e)
            self.say(f"  register_ontology -> PermissionDeniedError: {e}")

    def show_answerability(self, version: int) -> None:
        result = _result(
            self.office.get_evaluation_results(KG, version), "structural_answerability"
        )
        m = result.metrics
        self.answerability.append(
            (version, result.use_case_version or 0, m["answerable_questions"], m["questions"])
        )
        self.say(
            f"structural_answerability of v{version} against Use Case Version "
            f"{result.use_case_version}: {m['answerable_questions']}/{m['questions']} answerable"
        )
        for d in result.details:
            if d.data and d.data["status"] != "answerable":
                self.say(f"  - {d.item}: {d.message}")

    # --- 3. build ---------------------------------------------------------------------

    def first_run(self) -> None:
        self.act("3. Build: the first Construction Run, matching ORCID records by name")
        with self.office.start_run(KG) as run:
            run.log_params({"orcid_matching": "by-name", "sources": "data/*, orcid-sync.json"})
            stats = build(self.graph, ontology=run.declared_ontology, database=SCOPE.database)
            run.log_metrics(_metrics(stats))
        self.run1 = self.office.get_run(run.id)
        self.say(
            f"Run {self.run1.id[:8]} declared v{self.run1.ontology_version}; wrote {stats.nodes} nodes "
            f"and {stats.relationships} relationships; ORCID records: {stats.orcid_matched} matched, "
            f"{stats.orcid_added} became new Author nodes"
        )
        self.show_run(self.run1)

        self.say("", "A token with grants on another Knowledge Graph asks about this run:")
        self.outsider_errors: dict[str, str] = {}
        for label, call in (
            ("get_run(<run 1>)", lambda: self.outsider.get_run(self.run1.id)),
            ("get_run(<unknown id>)", lambda: self.outsider.get_run(UNKNOWN_RUN_ID)),
            (f"get_knowledge_graph({KG})", lambda: self.outsider.get_knowledge_graph(KG)),
        ):
            try:
                call()
            except stetiq.StetiqError as e:
                self.outsider_errors[label] = f"{type(e).__name__}: {e}"
                self.say(f"  {label} -> {self.outsider_errors[label]}")

        self.say("", "CI gates the Candidate:")
        self.gates_candidate = self.ci.evaluate_gates(KG, CONFIG, version=2)
        self.show_gates(self.gates_candidate)

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
        results = self.office.get_run_evaluation_results(run.id)
        m = _result(results, "competency_question_execution").metrics
        self.say(
            f"competency_question_execution: {m['passed_questions']}/{m['questions']} passed "
            f"(pass_ratio {m['pass_ratio']:.3f})"
        )
        dedupe = _result(results, "author_dedupe").metrics
        self.say(
            f"author_dedupe (custom run Evaluator): {dedupe['authors']:.0f} Author nodes, "
            f"{dedupe['duplicate_authors']:.0f} duplicates in {dedupe['duplicate_groups']:.0f} groups"
        )

    def show_gates(self, result: stetiq.GateResult) -> None:
        subject = (
            f"Construction Run {result.subject_id[:8]} (stands for v{result.ontology_version})"
            if result.subject_kind == "construction_run"
            else f"Ontology Version {result.ontology_version}"
        )
        self.say(
            f"Gates from stetiq.yaml on {subject}: "
            f"{'all passed' if result.passed else f'{len(result.failed)} of {len(result.outcomes)} failed'}"
        )
        for o in result.outcomes:
            self.say(f"  {'PASS' if o.passed else 'FAIL'}  {o.gate.name}")
            for reason in o.reasons[:3]:
                self.say(f"        - {reason}")

    # --- 4. the Use Case evolves ------------------------------------------------------

    def evolve_use_case(self) -> None:
        self.act("4. The Use Case evolves: two new Competency Questions, judged on registration")
        for question in (SELF_CITATION_QUESTION, ORCID_COAUTHORS_QUESTION):
            use_case = self.office.add_competency_question(KG, question)
            self.say(f"Added {question['id']}: Use Case Version {use_case.number}")
            # register_use_case judges the latest Ontology Version only (the Candidate v2).
            self.show_answerability(2)
        self.say(
            "", "Ontology Version 1 keeps its Use Case Version 1 verdict until it is re-judged:"
        )
        self.office.evaluate(KG, 1, use_case_version=3)
        self.show_answerability(1)

    # --- 5. improve -------------------------------------------------------------------

    def improve(self) -> None:
        self.act("5. Improve: revise the Ontology, fix the loader, gate and promote")
        v3 = self.office.register_ontology(KG, ONTOLOGY / "v3.yaml")
        diff = self.office.diff_ontology_versions(KG, 1, v3.number)
        self.say(
            f"Registered ontology/v3.yaml as v{v3.number}; diff v1 -> v{v3.number} is "
            f"{diff.classification} ({len(diff.changes)} changes)"
        )
        self.show_answerability(v3.number)

        self.say(
            "",
            f"Second Construction Run against v{v3.number}, still matching ORCID records by name",
        )
        with self.office.start_run(KG, ontology_version=v3.number) as run:
            run.log_params({"orcid_matching": "by-name"})
            stats = build(self.graph, ontology=run.declared_ontology, database=SCOPE.database)
            run.log_metrics(_metrics(stats))
        self.run2 = self.office.get_run(run.id)
        self.show_run(self.run2)
        self.gates_run2 = self.ci.evaluate_gates(KG, CONFIG, run=self.run2.id)
        self.show_gates(self.gates_run2)

        self.say(
            "",
            "The nightly CI run goes through the Construction Entry Point of stetiq.yaml, now with --merge-by-orcid",
        )
        entry_point = EntryPoint.from_config(load_config(CONFIG))
        self.nightly = self.ci.run_entry_point(
            KG, entry_point, ontology_version=v3.number, cwd=EXAMPLE_DIR
        )
        self.say(
            f"Run {self.nightly.id[:8]}: exit code {self.nightly.params['entry_point.exit_code']}"
        )
        self.show_run(self.nightly)
        self.gates_nightly = self.ci.evaluate_gates(KG, CONFIG, run=self.nightly.id)
        self.show_gates(self.gates_nightly)
        if self.gates_nightly.passed:
            self.ci.set_alias(KG, "production", v3.number)
            self.say(f"Promoted: production -> v{v3.number} by the CI bot")
        else:
            self.say("Gates failed: not promoting.")
        self.show_promotions()

    def show_promotions(self) -> None:
        self.say(f"Promotion audit log (the CI Client was built with actor={self.ci.actor!r}):")
        for p in self.office.list_promotions(KG):
            self.say(
                f"  {p.promoted_at:%Y-%m-%d %H:%M} {p.alias}: v{p.from_version or '-'} -> v{p.to_version} "
                f"by {p.actor}, Gate result {p.gate_result or '-'}"
            )

    # --- 6. proposals -----------------------------------------------------------------

    def proposals(self) -> None:
        self.act("6. Proposals: the library suggests two changes; the Gates judge them")
        self.say(
            "The library checks its proposals client-side (diff_ontologies needs no permission):"
        )
        for name in ("proposal-venue-hierarchy", "proposal-rename-cites"):
            diff = self.library.diff_ontologies(ONTOLOGY / "v3.yaml", ONTOLOGY / f"{name}.yaml")
            self.say(f"  v3 -> {name}: {diff.classification} ({len(diff.changes)} changes)")

        self.say(
            "", "The research office registers the venue hierarchy and runs the loader against it"
        )
        v4 = self.office.register_ontology(KG, ONTOLOGY / "proposal-venue-hierarchy.yaml")
        with self.office.start_run(KG, ontology_version=v4.number) as run:
            run.log_params({"orcid_matching": "by-orcid", "trial": True})
            stats = build(
                self.graph,
                ontology=run.declared_ontology,
                merge_by_orcid=True,
                database=SCOPE.database,
            )
            run.log_metrics(_metrics(stats))
        self.trial_run = self.office.get_run(run.id)
        self.show_run(self.trial_run)
        self.gates_venues = self.ci.evaluate_gates(KG, CONFIG, version=v4.number)
        self.show_gates(self.gates_venues)
        if self.gates_venues.passed:
            self.office.set_alias(KG, "staging", v4.number)
            self.say(
                f"Promoted: staging -> v{v4.number} by the research office; production stays on v3"
            )

        self.say("", "The rename is registered too, so the verdict is on record:")
        v5 = self.office.register_ontology(KG, ONTOLOGY / "proposal-rename-cites.yaml")
        self.show_answerability(v5.number)
        self.gates_rename = self.ci.evaluate_gates(KG, CONFIG, version=v5.number)
        self.show_gates(self.gates_rename)

    # --- 7. finish --------------------------------------------------------------------

    def finish(self) -> None:
        self.act("7. Browse")
        versions = self.office.list_ontology_versions(KG)
        self.say(
            f"{KG}: Ontology Versions "
            + ", ".join(f"v{v.number} ({v.origin})" for v in versions)
            + f"; production -> v{self.office.get_contract_version(KG).number}"
            + f"; Use Case Versions {[u.number for u in self.office.list_use_case_versions(KG)]}"
        )
        here = EXAMPLE_DIR.resolve() == Path.cwd().resolve()
        self.say(
            "",
            "Open the web UI on the server's database"
            + ("" if here else f" (from {EXAMPLE_DIR})")
            + ":",
            f"  uv run stetiq ui --tracking-uri {self.database_url}",
            "",
            "Or run `stetiq server` over the same database and use the CLI with a token (README.md).",
        )


def _result(results: list[stetiq.EvaluationResult], evaluator: str) -> stetiq.EvaluationResult:
    return next(r for r in results if r.evaluator == evaluator)


def _metrics(stats) -> dict[str, float]:
    return {
        "nodes": stats.nodes,
        "relationships": stats.relationships,
        "orcid_matched": stats.orcid_matched,
        "orcid_added": stats.orcid_added,
        "co_authored": stats.co_authored,
    }


def run_demo(
    *,
    tracking_uri: str = DEFAULT_TRACKING_URI,
    graph_file: Path = DEFAULT_GRAPH_FILE,
    http: TestClient | None = None,
    quiet: bool = False,
) -> Demo:
    """Run the story. `tracking_uri` is the server's database (sqlite:///... or
    postgresql://...); `http` is an already started in-process server, else one is
    started for the duration of the walkthrough."""
    if http is None:
        with TestClient(create_app(database_url=tracking_uri)) as started:
            return run_demo(
                tracking_uri=tracking_uri, graph_file=graph_file, http=started, quiet=quiet
            )
    demo = Demo(database_url=tracking_uri, http=http, graph_file=graph_file, quiet=quiet)
    demo.tokens_and_clients()
    demo.declare()
    demo.first_run()
    demo.evolve_use_case()
    demo.improve()
    demo.proposals()
    demo.finish()
    return demo


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--tracking-uri",
        default=DEFAULT_TRACKING_URI,
        help="the server's database (what `stetiq ui --tracking-uri` reads afterwards)",
    )
    parser.add_argument("--graph-file", default=str(DEFAULT_GRAPH_FILE))
    parser.add_argument(
        "--reset",
        action="store_true",
        help="delete the server's database and the graph file first",
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
