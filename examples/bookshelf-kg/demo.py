"""Walk through stetiq on the smallest Knowledge Graph that still tells the whole story:
a town library's catalogue.

    cd examples/bookshelf-kg
    uv run python demo.py            # fully offline, deterministic
    uv run stetiq ui                 # then browse the result

Everything is in-process: the tracking database is .stetiq/stetiq.db and the Graph
Source is stetiq's InMemoryGraphSource, filled straight from data/. README.md tells
the story act by act.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import sys
from collections import Counter
from pathlib import Path

import stetiq
from stetiq import GraphSourceScope, InMemoryGraphSource
from stetiq.use_case import parse_use_case_yaml

EXAMPLE_DIR = Path(__file__).resolve().parent
DATA = EXAMPLE_DIR / "data"
ONTOLOGY = EXAMPLE_DIR / "ontology"
CONFIG = EXAMPLE_DIR / "stetiq.yaml"
USE_CASE = EXAMPLE_DIR / "use-case.yaml"
DEFAULT_TRACKING_URI = f"sqlite:///{EXAMPLE_DIR / '.stetiq' / 'stetiq.db'}"

KG = "town-library"
# The in-memory Graph Source has one database; the Knowledge Graph is bound to it.
SCOPE = GraphSourceScope(database="library")
# The day the walkthrough happens on: `overdue-loans` in use-case.yaml compares with it.
AS_OF = dt.date(2026, 10, 30)

DESCRIPTION = """The town library's catalogue as a Knowledge Graph: **books** and their
**authors**, the **members** and **branches**, and every **loan** from the circulation log.

Built in-process by `examples/bookshelf-kg/demo.py` from four small files in `data/`;
the Competency Questions are the head librarian's questions in `use-case.yaml`."""


class Demo:
    """The state the walkthrough builds up (the test reads it back)."""

    def __init__(self, *, tracking_uri: str, quiet: bool) -> None:
        self.tracking_uri = tracking_uri
        self.quiet = quiet
        self.graph = InMemoryGraphSource()
        # One user: the head librarian, who also moves the Aliases. The audit log names her.
        self.client = stetiq.Client(tracking_uri, graph_source=self.graph, actor="ines.ferreira")

    # --- output -----------------------------------------------------------------------

    def say(self, *lines: str) -> None:
        if not self.quiet:
            print(*lines, sep="\n", flush=True)

    def act(self, title: str) -> None:
        self.say("", f"=== {title} ", "")

    # --- 1. declare -------------------------------------------------------------------

    def declare(self) -> None:
        self.act("1. Declare: the Knowledge Graph, its first Ontology Version and the Use Case")
        client = self.client
        client.create_knowledge_graph(KG, ontology=ONTOLOGY / "v1.yaml")
        client.set_knowledge_graph_description(KG, DESCRIPTION)
        client.bind_graph_source(KG, SCOPE)
        v1 = client.get_ontology_version(KG, 1)
        self.say(
            f"Created {KG} from ontology/v1.yaml: Ontology Version 1 ({v1.content_hash[:12]}), "
            "production -> v1",
            f"Bound it to the Graph Source scope database={SCOPE.database} (in memory)",
        )
        # Registering identical content is a no-op: the content hash finds the version.
        self.v1_again = client.register_ontology(KG, ONTOLOGY / "v1.yaml")
        self.say(
            f"Registered ontology/v1.yaml again: still Ontology Version {self.v1_again.number} "
            f"({self.v1_again.content_hash[:12]}), nothing new"
        )
        use_case = client.register_use_case(KG, USE_CASE)
        self.say(
            f"Registered the Use Case (Use Case Version {use_case.number}): "
            f"{len(use_case.use_case.competency_questions)} Competency Questions"
        )
        self.show_answerability(1)

        # An Ontology Diff needs no registered versions: compare the two files in the repo.
        self.file_diff = client.diff_ontologies(
            ONTOLOGY / "v1.yaml", ONTOLOGY / "v2-hierarchy.yaml"
        )
        self.say(
            "",
            f"Ontology Diff of the files v1.yaml -> v2-hierarchy.yaml: {self.file_diff.classification} "
            f"({len(self.file_diff.changes)} changes); the ones above additive:",
        )
        for c in self.file_diff.changes:
            if c.classification != "additive":
                self.say(f"  - {c.classification} {c.kind} {c.concept}: {c.detail}")
        self.v2 = client.register_ontology(KG, ONTOLOGY / "v2-hierarchy.yaml")
        self.say(f"Registered ontology/v2-hierarchy.yaml as Ontology Version {self.v2.number}")

    def show_answerability(self, version: int) -> None:
        result = _result(
            self.client.get_evaluation_results(KG, version), "structural_answerability"
        )
        m = result.metrics
        self.say(
            f"structural_answerability of v{version}: {m['answerable_questions']}/{m['questions']} "
            f"answerable, {m['unanswerable_questions']} unanswerable, "
            f"{m['unmapped_questions']} unmapped (ratio {m['answerable_ratio']:.3f})"
        )
        for d in result.details:
            if d.data and d.data["status"] != "answerable":
                self.say(f"  - {d.item}: {d.message}")

    # --- 2. hierarchy -----------------------------------------------------------------

    def hierarchy(self) -> None:
        self.act("2. Hierarchy: Person above Author and Member, and a constraint declared twice")
        client = self.client
        self.show_structure(self.v2.number)
        # v1 was a sketch nobody built against. The structure the branches agreed on is v2,
        # so the Contract Alias moves there before anything is built: from now on every
        # Ontology Diff and every Construction Run starts from v2. No Gate has judged v2,
        # which the audit log will show as "-".
        client.set_alias(KG, "production", self.v2.number)
        self.say(f"production -> v{self.v2.number}: the structure the library builds against")
        self.v3 = client.register_ontology(KG, ONTOLOGY / "v3-deprecate-genre.yaml")
        self.say(
            "",
            f"Registered ontology/v3-deprecate-genre.yaml as Ontology Version {self.v3.number}, "
            "which declares the uniqueness of the name once, on Person:",
        )
        self.show_structure(self.v3.number)

    def show_structure(self, version: int) -> None:
        results = self.client.get_evaluation_results(KG, version)
        h = _result(results, "hierarchy").metrics
        self.say(
            f"hierarchy of v{version}: max_depth={h['max_depth']:g}, "
            f"root_node_types={h['root_node_types']:g}, max_children={h['max_children']:g}"
        )
        consistency = _result(results, "constraint_consistency")
        self.say(
            f"constraint_consistency of v{version}: "
            f"inconsistencies={consistency.metrics['inconsistencies']:g}"
        )
        for d in consistency.details:
            self.say(f"  - {d.item}: {d.message}")

    # --- 3. deprecate -----------------------------------------------------------------

    def deprecate(self) -> None:
        self.act("3. Deprecate: Subject replaces Genre, first as a warning, then for real")
        client = self.client
        self.diff_v2_v3 = client.diff_ontology_versions(KG, self.v2.number, self.v3.number)
        self.say(
            f"Ontology Diff v{self.v2.number} -> v{self.v3.number}: {self.diff_v2_v3.classification}"
        )
        for c in self.diff_v2_v3.changes:
            self.say(f"  - {c.classification} {c.kind} {c.concept}: {c.detail}")
        self.v4 = client.register_ontology(KG, ONTOLOGY / "v4-remove-genre.yaml")
        self.diff_v3_v4 = client.diff_ontology_versions(KG, self.v3.number, self.v4.number)
        self.say(
            "",
            f"Registered ontology/v4-remove-genre.yaml as Ontology Version {self.v4.number}",
            f"Ontology Diff v{self.v3.number} -> v{self.v4.number}: {self.diff_v3_v4.classification}",
        )
        for c in self.diff_v3_v4.changes:
            self.say(f"  - {c.classification} {c.kind} {c.concept}: {c.detail}")

    # --- 4. build ---------------------------------------------------------------------

    def build(self) -> None:
        self.act("4. Build: one Construction Run loads the catalogue against v3")
        client = self.client
        use_case = parse_use_case_yaml(USE_CASE.read_text(encoding="utf-8"))
        # v3 is under review, not yet the contract: say so instead of taking the default.
        with client.start_run(KG, ontology_version=self.v3.number) as run:
            run.log_params(
                {
                    "sources": "catalogue.csv, members.csv, loans.csv, branches.json",
                    "as_of": AS_OF.isoformat(),
                }
            )
            counts = load_library(self.graph, database=SCOPE.database)
            # The executed Competency Questions read the Graph Source. The in-memory
            # source cannot run Cypher, so the loader registers each query's rows; a real
            # installation runs the same Cypher on Neo4j.
            register_answers(self.graph, use_case, database=SCOPE.database)
            run.log_metrics({k: v for k, v in counts.items() if k in ("books", "loans")})
            run.log_metrics({"nodes": counts["nodes"], "relationships": counts["relationships"]})
        self.run = client.get_run(run.id)
        self.say(
            f"Run {self.run.id[:8]} declared v{self.run.ontology_version}: wrote "
            f"{counts['nodes']} nodes and {counts['relationships']} relationships "
            f"({counts['books']} books, {counts['loans']} loans)",
            f"Status: {self.run.status}",
        )
        if self.run.conformance is not None:
            self.say(
                f"Conformance {self.run.conformance.score:.3f} with "
                f"{len(self.run.conformance.mismatches)} mismatches"
            )
            for m in self.run.conformance.mismatches:
                self.say(f"  - {m.kind} {m.subject_kind} {m.subject}")
        self.say(
            "Evolution Mode evolving, but nothing undeclared was observed: "
            f"Candidate {self.run.candidate_version}"
        )
        execution = _result(
            client.get_run_evaluation_results(self.run.id), "competency_question_execution"
        )
        m = execution.metrics
        self.say(
            f"competency_question_execution: {m['passed_questions']:g}/{m['questions']:g} passed, "
            f"{m['skipped_questions']:g} skipped (no query); pass_ratio {m['pass_ratio']:.3f}"
        )
        for d in execution.details:
            self.say(f"  - {d.item}: {d.message}")
        self.say("")
        self.show_answerability(self.v3.number)

    # --- 5. promote -------------------------------------------------------------------

    def promote(self) -> None:
        self.act("5. Promote: gate, move the Aliases, and roll back with an audit trail")
        client = self.client
        self.gates_v2 = client.evaluate_gates(KG, CONFIG, version=self.v2.number)
        self.show_gates(self.gates_v2)
        self.gates_v3 = client.evaluate_gates(KG, CONFIG, version=self.v3.number)
        self.show_gates(self.gates_v3)
        if self.gates_v3.passed:
            client.set_alias(KG, "staging", self.v3.number)
            client.set_alias(KG, "production", self.v3.number)
            self.say(f"Promoted: staging -> v{self.v3.number}, production -> v{self.v3.number}")
        else:
            self.say("Gates failed: not promoting")
        self.gates_v4 = client.evaluate_gates(KG, CONFIG, version=self.v4.number)
        self.show_gates(self.gates_v4)
        self.say(
            "",
            "The branches' report script still reads Genre and is not ready for the deprecation: "
            f"roll production back to v{self.v2.number}",
        )
        client.set_alias(KG, "production", self.v2.number)
        self.promotions = client.list_promotions(KG)
        self.say("Promotion audit log (stetiq alias log):")
        for p in self.promotions:
            self.say(
                f"  {p.promoted_at:%Y-%m-%d %H:%M} {p.alias}: v{p.from_version or '-'} -> "
                f"v{p.to_version} by {p.actor}, Gate result {p.gate_result or '-'}"
            )

    def show_gates(self, result: stetiq.GateResult) -> None:
        self.say(
            f"Gates from stetiq.yaml on Ontology Version {result.ontology_version}: "
            f"{'all passed' if result.passed else f'{len(result.failed)} of {len(result.outcomes)} failed'}"
        )
        for o in result.outcomes:
            self.say(f"  {'PASS' if o.passed else 'FAIL'}  {o.gate.name}")
            if not o.passed:
                for reason in o.reasons[:3]:
                    self.say(f"        - {reason}")

    # --- 6. finish --------------------------------------------------------------------

    def finish(self) -> None:
        self.act("6. Browse")
        versions = self.client.list_ontology_versions(KG)
        self.say(
            f"{KG}: Ontology Versions "
            + ", ".join(f"v{v.number} ({v.origin})" for v in versions)
            + f"; production -> v{self.client.get_contract_version(KG).number}, "
            f"staging -> v{self.client.get_alias(KG, 'staging').version}"
        )
        here = EXAMPLE_DIR.resolve() == Path.cwd().resolve()
        self.say(
            "",
            "Open the web UI and the CLI on this tracking database"
            + ("" if here else f" (from {EXAMPLE_DIR})")
            + ":",
            "  uv run stetiq ui                      # http://127.0.0.1:5000/ui",
            f"  uv run stetiq ontology list {KG}",
            f"  uv run stetiq ontology diff {KG} 3 4",
            f"  uv run stetiq runs evaluations {self.run.id}",
            "  uv run stetiq gate --version 3        # the Knowledge Graph comes from stetiq.yaml",
            f"  uv run stetiq alias log {KG}",
        )


def _result(results: list[stetiq.EvaluationResult], evaluator: str) -> stetiq.EvaluationResult:
    return next(r for r in results if r.evaluator == evaluator)


# --- the library's extraction workflow ---------------------------------------------------


def _read_csv(name: str) -> list[dict[str, str]]:
    with (DATA / name).open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def _date(text: str) -> dt.date | None:
    return dt.date.fromisoformat(text) if text else None


def load_library(graph: InMemoryGraphSource, *, database: str) -> dict[str, int]:
    """Write the four data files into the Graph Source as nodes and relationships.

    A node carries its most specific label only (an author is `Author`, not
    `Author:Person`); stetiq knows an Author has a `name` because the Declared
    Ontology says Author's parent Person declares it. The two head librarians are the
    only plain `Person` nodes. Returns counts only: nothing else leaves the Graph Source.
    """
    relationships = 0

    def link(start: int, type_: str, end: int) -> None:
        nonlocal relationships
        graph.add_relationship(start, type_, end)
        relationships += 1

    branches: dict[str, int] = {}
    for b in json.loads((DATA / "branches.json").read_text(encoding="utf-8")):
        branches[b["code"]] = graph.add_node(
            ["Branch"], {"code": b["code"], "name": b["name"]}, database=database
        )
        librarian = graph.add_node(["Person"], {"name": b["head_librarian"]}, database=database)
        link(librarian, "MANAGES", branches[b["code"]])

    catalogue = _read_csv("catalogue.csv")
    authors: dict[str, int] = {}
    genres: dict[str, int] = {}
    subjects: dict[str, int] = {}
    books: dict[str, int] = {}
    for row in catalogue:
        book = graph.add_node(
            ["Book"],
            {"isbn": row["isbn"], "title": row["title"], "year": int(row["year"])},
            database=database,
        )
        books[row["isbn"]] = book
        if row["author"] not in authors:
            authors[row["author"]] = graph.add_node(
                ["Author"], {"name": row["author"]}, database=database
            )
        link(authors[row["author"]], "WROTE", book)
        link(book, "HELD_AT", branches[row["branch"]])
        # Both the deprecated Genre and its replacement Subject, as v3 declares: the
        # shelf tags stay until every reader of the Knowledge Graph has moved on.
        if row["genre"] not in genres:
            genres[row["genre"]] = graph.add_node(
                ["Genre"], {"name": row["genre"]}, database=database
            )
        link(book, "IN_GENRE", genres[row["genre"]])
        if row["subject"] not in subjects:
            subjects[row["subject"]] = graph.add_node(
                ["Subject"], {"heading": row["subject"]}, database=database
            )
        link(book, "HAS_SUBJECT", subjects[row["subject"]])

    members: dict[str, int] = {}
    for row in _read_csv("members.csv"):
        members[row["card"]] = graph.add_node(
            ["Member"], {"name": row["name"], "card": row["card"]}, database=database
        )
        link(members[row["card"]], "MEMBER_OF", branches[row["branch"]])

    loans = _read_csv("loans.csv")
    for row in loans:
        loan = graph.add_node(
            ["Loan"],
            {
                "id": row["loan_id"],
                "borrowed": _date(row["borrowed"]),
                "due": _date(row["due"]),
                "returned": _date(row["returned"]),
            },
            database=database,
        )
        link(members[row["card"]], "BORROWED", loan)
        link(loan, "OF_BOOK", books[row["isbn"]])

    nodes = (
        len(branches) * 2
        + len(books)
        + len(authors)
        + len(genres)
        + len(subjects)
        + len(members)
        + len(loans)
    )
    return {
        "books": len(books),
        "loans": len(loans),
        "nodes": nodes,
        "relationships": relationships,
    }


def register_answers(
    graph: InMemoryGraphSource, use_case: stetiq.UseCase, *, database: str
) -> None:
    """Register, per Competency Question with a query, the rows Neo4j would return.

    The rows are computed from the same files the loader read, so the answers agree
    with the Knowledge Graph. They live in the Graph Source only; stetiq keeps the
    row count and the verdict (ADR 0001).
    """
    catalogue = {row["isbn"]: row for row in _read_csv("catalogue.csv")}
    members = {row["card"]: row for row in _read_csv("members.csv")}
    branches = {b["code"]: b["name"] for b in json.loads((DATA / "branches.json").read_text())}
    loans = _read_csv("loans.csv")

    books_per_author = Counter(row["author"] for row in catalogue.values())
    overdue = [
        {"loan": row["loan_id"], "book": catalogue[row["isbn"]]["title"]}
        for row in loans
        if not row["returned"] and dt.date.fromisoformat(row["due"]) < AS_OF
    ]
    members_per_branch = Counter(branches[row["branch"]] for row in members.values())
    loans_per_book = Counter(catalogue[row["isbn"]]["title"] for row in loans)
    answers = {
        "books-per-author": [{"author": a, "books": n} for a, n in books_per_author.most_common()],
        "overdue-loans": overdue,
        "members-per-branch": [
            {"branch": b, "members": n} for b, n in sorted(members_per_branch.items())
        ],
        "popular-books": [{"book": b, "loans": n} for b, n in loans_per_book.most_common()],
    }
    for question in use_case.competency_questions:
        if question.query:
            graph.add_query_result(question.query, answers[question.id], database=database)


# --- entry points ----------------------------------------------------------------------


def run_demo(*, tracking_uri: str = DEFAULT_TRACKING_URI, quiet: bool = False) -> Demo:
    demo = Demo(tracking_uri=tracking_uri, quiet=quiet)
    demo.say(f"stetiq {demo.tracking_uri}; Graph Source: in memory")
    demo.declare()
    demo.hierarchy()
    demo.deprecate()
    demo.build()
    demo.promote()
    demo.finish()
    return demo


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--tracking-uri", default=DEFAULT_TRACKING_URI)
    parser.add_argument("--reset", action="store_true", help="delete the tracking database first")
    args = parser.parse_args(argv)

    db = (
        Path(args.tracking_uri.removeprefix("sqlite:///"))
        if args.tracking_uri.startswith("sqlite:///")
        else None
    )
    if args.reset:
        if db is not None and db.exists():
            db.unlink()
    elif db is not None and db.exists():
        print(
            f"{db} already holds a previous walkthrough; pass --reset to start over",
            file=sys.stderr,
        )
        return 1
    if db is not None:
        db.parent.mkdir(parents=True, exist_ok=True)
    try:
        run_demo(tracking_uri=args.tracking_uri)
    except stetiq.StetiqError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
