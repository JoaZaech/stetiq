# Town library: the smallest stetiq walkthrough

The head librarian of a two-branch town library wants a Knowledge Graph of the catalogue:
books, authors, members, branches and the circulation log. The data is tiny and nobody
needs an extraction workflow; what she needs is to see how stetiq versions an Ontology,
judges it against her questions, and records who moved `production` where and why. Where
[`plant-kg`](../plant-kg/README.md) shows the whole operation (an entry point, Drift,
Candidates, custom Evaluators), this example is the "hello world": one in-process
Construction Run, four hand-registered Ontology Versions, and every step a single SDK call
with its CLI twin.

Everything runs offline and deterministically: SQLite under `.stetiq/` for tracking, and
stetiq's own `InMemoryGraphSource`, filled straight from `data/`, as the Graph Source.

## Run it

```bash
cd examples/bookshelf-kg
uv run python demo.py                 # fully offline, deterministic
uv run stetiq ui                      # browse the result at http://127.0.0.1:5000/ui
```

`demo.py --reset` starts over. `uv run pytest tests/test_example_bookshelf_kg.py` (from the
repo root) runs the same story and pins every number below. The CLI works on the same
tracking database from this folder (it reads `./stetiq.yaml` and `.stetiq/stetiq.db`).

## The data

| File | Rows | What it holds |
| --- | --- | --- |
| `data/catalogue.csv` | 7 books | ISBN, title, author, year, the loose shelf `genre` and the controlled `subject` heading, holding branch |
| `data/members.csv` | 4 members | Card number, name, home branch |
| `data/loans.csv` | 12 loans | Borrowed, due and returned dates; five still open on 2026-10-30, three overdue |
| `data/branches.json` | 2 branches | Code, name, address, head librarian |

`data/README.md` says where a real library gets each file (MARC 21 exports, the ILS patron
and circulation files). Loaded, this is 41 nodes and 58 relationships.

## The story

**1. Declare.** `ontology/v1.yaml` is deliberately minimal: `Book`, `Author`, `WROTE`.
It becomes Ontology Version 1 of the Knowledge Graph `town-library`, with `production`
pointing at it. Registering the identical file again returns the same version with the
same content hash: nothing new. `use-case.yaml` names four Consumers: the online
catalogue, the overdue reminder bot, the monthly lending report to the town council and
the acquisitions team. `popular-books` and `books-per-author` each serve two Tasks;
`authors-who-are-members` serves none. Their Tasks need six Competency Questions; judged structurally against v1, 1 of 6 is answerable (ratio 0.167), four miss
Concepts v1 lacks, one is unmapped on purpose. Before registering anything else,
`client.diff_ontologies` compares two files in the repo, `v1.yaml` and
`v2-hierarchy.yaml`: 16 changes, overall **breaking**, because lifting `name` from `Author`
to its new parent removes `Author.name`. Then v2 is registered.

```bash
uv run stetiq kg create town-library --ontology ontology/v1.yaml
uv run stetiq kg bind-source town-library --database library
uv run stetiq ontology register town-library ontology/v1.yaml      # still Ontology Version 1
uv run stetiq use-case register town-library use-case.yaml
uv run stetiq ontology register town-library ontology/v2-hierarchy.yaml
uv run stetiq ontology list town-library                           # v1 and v2, both "registered"
uv run stetiq ontology diff town-library 1 2                       # the CLI diffs registered versions
```

**2. Hierarchy.** v2 introduces `Person` as the parent of `Author` and `Member`
(`parent:`), plus `Branch`, `Loan` and `Genre`. The `hierarchy` Evaluator reports
`max_depth` 2, `root_node_types` 5, `max_children` 2. v2 also declares uniqueness of the
name at `Person` **and** again at `Author`; `constraint_consistency` reports 1
inconsistency, "Author.name: already unique via Person". The librarian moves `production`
to v2 (the structure the branches agreed to build against; no Gate has judged it yet) and
registers `v3-deprecate-genre.yaml`, which declares the constraint once: 0 inconsistencies,
`root_node_types` 6.

```bash
uv run stetiq ontology evaluations town-library 2
uv run stetiq alias set town-library production 2 --actor ines.ferreira
uv run stetiq ontology register town-library ontology/v3-deprecate-genre.yaml
```

**3. Deprecate.** v3 marks `Genre` and `IN_GENRE` `deprecated: true` with `replacedBy:
Subject` / `HAS_SUBJECT`, and adds `Subject`. The Ontology Diff v2 -> v3 is
**deprecating**: two deprecations, three additive changes, nothing breaking. v4 removes
`Genre` outright and the diff v3 -> v4 is **breaking** (two removals). The
`no-breaking-changes` Gate in `stetiq.yaml` allows `max_classification: deprecating`, so
v3 will pass it and v4 will not.

```bash
uv run stetiq ontology register town-library ontology/v4-remove-genre.yaml
uv run stetiq ontology diff town-library 2 3        # Overall: deprecating
uv run stetiq ontology diff town-library 3 4        # Overall: breaking
```

**4. Build.** One Construction Run, opened with `client.start_run(..., ontology_version=3)`
because v3 is under review and not yet the Contract Alias. It loads the four files into the
Graph Source, logs params (`sources`, `as_of`) and metrics (7 books, 12 loans, 41 nodes,
58 relationships), and registers the rows each Cypher query would return so the executed
Competency Questions have answers. Conformance is **1.000** with 0 mismatches; the
Knowledge Graph is in evolving Evolution Mode, but nothing undeclared was observed, so no
Candidate appears. `competency_question_execution`: 4 of 4 queried questions pass (the
overdue one against its `expected_answer`, 3 rows), 2 skipped for having no query.
`structural_answerability` against v3: 5 of 6 (ratio 0.833); only the unmapped
`authors-who-are-members` remains.

```bash
uv run stetiq runs list town-library
uv run stetiq runs evaluations <run id>
```

**5. Promote.** The Gates are evaluated on v2 first: 3 of 5 fail (no Conformance for v2,
1 constraint inconsistency, answerable ratio 0.667 < 0.8). On v3 all 5 pass, so
`staging` and then `production` move to v3. v4 fails 2 of 5 (the breaking diff and no
Conformance). Then a rollback: the branches' report script still reads `Genre`, so
`production` goes back to v2. `stetiq alias log` shows five audit entries, each with its
actor and the latest Gate result of the version it moved to: v1 by stetiq (no Gate), v2
by the librarian (no Gate yet), `staging` and `production` to v3 (passed), and
`production` back to v2 (**failed**), on the record.

```bash
uv run stetiq gate --version 2                       # 3 of 5 fail, exit code 3
uv run stetiq gate --version 3                       # all passed
uv run stetiq alias set town-library staging 3 --actor ines.ferreira
uv run stetiq alias set town-library production 3 --actor ines.ferreira
uv run stetiq gate --version 4                       # 2 of 5 fail
uv run stetiq alias set town-library production 2 --actor ines.ferreira
uv run stetiq alias log town-library
```

## Files

| File | Role |
| --- | --- |
| `demo.py` | The walkthrough, act by act, including the loader. `run_demo()` returns the state for the test |
| `stetiq.yaml` | Knowledge Graph name and the five Gates (Ontology Diff, Conformance, three metric Gates) |
| `use-case.yaml` | The four Consumers, their Tasks and the six Competency Questions |
| `ontology/` | `v1`, `v2-hierarchy`, `v3-deprecate-genre`, `v4-remove-genre` |
| `data/` | The four source files and a README on their provenance |

Two things are left standing on purpose. `authors-who-are-members` stays unmapped until the
librarian gives it a query or a Concept mapping (ratio 0.833, what `questions-answerable`
guards). And `production` ends on v2 while `staging` is on v3: the audit log, not the
Gates, records that the rollback was a choice made against a passing version.

The in-memory Graph Source does not run Cypher: `demo.py` registers the result rows of the
four queries in `use-case.yaml` by query text. On a real installation, bind `town-library` to
Neo4j (`stetiq kg bind-source`), set `STETIQ_GRAPH_SOURCE_URI`, drop the `graph_source=`
argument and the `add_query_result` calls: the same Cypher runs against the live graph,
and the Ontology Versions, Use Case and Gates stay exactly as they are.
