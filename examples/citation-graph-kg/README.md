# Citation graph: stetiq in server mode, with API Tokens

A university's research office keeps a Knowledge Graph of the institution's research
output: papers, their authors, the venues they appeared in, the grants they acknowledge
and the citations between them. Three teams touch it: the research office owns the
Ontology, the library reads it and proposes changes, and a CI bot rebuilds the graph
every night. stetiq versions the Ontology, judges every Construction Run against the
office's Competency Questions, gates changes and records who promoted what.

Where the plant maintenance example runs the SDK in local mode for one person, this one
puts a stetiq server between everyone: every call goes over HTTP with an API Token, the
Use Case grows while the Ontology catches up, and the audit log names the token's user.

Everything still runs on your laptop with no services: the server runs inside the demo
process (FastAPI's `TestClient`) over a SQLite database, the "graph database" is a JSON
file, and the loader is deterministic.

## Run it

```bash
cd examples/citation-graph-kg
uv run python demo.py                                        # starts the in-process server
uv run stetiq ui --tracking-uri sqlite:///.stetiq/server.db  # browse the result at /ui
```

`demo.py --reset` starts over. `uv run pytest tests/test_example_citation_graph_kg.py`
runs the story as a test (it starts the server itself) and pins its outcomes.

To do the same against a real server, run one over the same database, issue a token the
way an administrator would (against the database, never over HTTP), and point the CLI at
the server with the token in the environment:

```bash
uv run stetiq server --database-url sqlite:///.stetiq/server.db           # terminal 1
uv run stetiq token create research-office --grant scholar-kg=edit \
    --database-url sqlite:///.stetiq/server.db                            # prints stq_... once
export STETIQ_TRACKING_URI=http://127.0.0.1:5000 STETIQ_TOKEN=stq_...    # terminal 2
uv run stetiq gate-results scholar-kg
uv run stetiq alias log scholar-kg
uv run stetiq ontology diff scholar-kg 1 3
```

## The data

| Source | Rows | What it holds |
| --- | --- | --- |
| `data/papers.json` | 60 papers, 2016 to 2025 | Title, year, venue, DOI-like id, one-line abstract, author ids, grant ids |
| `data/authors.csv` | 120 authors | Name and department, as the publication database spells them |
| `data/venues.csv` | 12 venues | Six journals, six conferences |
| `data/grants.csv` | 10 grants | Grant number, title and a `funder` column the first Ontology does not know about |
| `data/citations.csv` | 125 edges | Which paper cites which |
| `data/orcid-sync.json` | 40 records | ORCID iDs with each person's works, in the registry's own spelling: two names disagree with `authors.csv` (`Anne Marie Dubois`, `Jose Alvarez Reyes`) |

The loader (`scholar_pipeline.py`) is driven by the Declared Ontology stetiq hands the
run: it derives `CO_AUTHORED` edges only once the Ontology declares them and labels a
`Venue` as `Journal` or `Conference` only once those subtypes exist. The ORCID sync is
matched to authors by name spelling, or by shared works with `--merge-by-orcid`.

## The story

**1. Server.** One stetiq server, four API Tokens: `research-office` (edit on `scholar-kg`),
`library` (read), `ci-bot` (edit, but its Client is built with `actor="someone-else"` on
purpose) and `events-team` (edit on a different Knowledge Graph). The custom Evaluator
`author_dedupe` is registered on the two Clients that end Construction Runs; it runs in
the SDK process, and only its aggregates reach the server.

**2. Declare.** `ontology/v1.yaml` becomes Ontology Version 1, `production` points at it,
and the Graph Source scope `database=scholar` is bound. `use-case.yaml` holds five
Competency Questions (Use Case Version 1), all answerable by v1. The library's token
lists Ontology Versions but `register_ontology` is a `PermissionDeniedError` naming the
token, the user and the missing `edit`.

**3. Build.** The first Construction Run writes 204 nodes and 400 relationships against
v1. The Observed Schema has two undeclared properties, `Author.orcid` and `Grant.funder`,
so Conformance is 0.917 and the evolving Evolution Mode registers **Candidate v2**. All
five executed questions pass, including the expected answer for the most-cited paper.
`author_dedupe` finds 122 Author nodes with 2 duplicates: the two ORCID records spelled
differently became second nodes for the same people. The events team's token asks for
this run and gets the uniform 404 (`NotFoundError`), the same answer as for a made-up id;
asking for `scholar-kg` by name is a plain denial, since the name is already in the URL.
CI gates the Candidate: 2 of 6 Gates fail (`graph-conforms`, `no-duplicate-authors`).

**4. The Use Case evolves.** The research office adds `self-citation-share` (Use Case
Version 2) and `orcid-coauthors` (Use Case Version 3) with `add_competency_question`. Each
registration judges the latest Ontology Version only, the Candidate v2: 6/6, then 6/7
(`CO_AUTHORED` is missing). Ontology Version 1 keeps its Use Case Version 1 verdict until
it is re-judged with `evaluate(..., use_case_version=3)`: 5/7, because both new
questions need `Author.orcid`.

**5. Improve.** `ontology/v3.yaml` adopts `Author.orcid` and `Grant.funder` from the
Candidate and adds `CO_AUTHORED`: an additive Ontology Diff of 3 changes, 7/7 answerable.
The second run reaches Conformance 1.0 with 7/7 questions passing, and still fails one
Gate: `author_dedupe.duplicate_authors = 2`. The nightly CI run goes through the Construction
Entry Point from `stetiq.yaml` with `--merge-by-orcid`: 120 Author nodes, 0 duplicates,
all 6 Gates pass, and the CI bot promotes `production` to v3. The audit log says
`by ci-bot`: the server records the token's user and ignores the Client's actor.

**6. Proposals.** The library diffs its two proposals client-side (`diff_ontologies` needs
no permission): `proposal-venue-hierarchy.yaml` (`Journal` and `Conference` with
`parent: Venue`) is additive, `proposal-rename-cites.yaml` is breaking. The office
registers the hierarchy as v4, a trial run reaches Conformance 1.0, all Gates pass and
`staging` moves to v4 while `production` stays on v3. The rename is registered as v5 so the
verdict is on record: 4 of 6 Gates fail, two questions lose `CITES` (5/7 answerable,
ratio 0.714 under the 0.85 floor), and nothing is promoted.

**7. Browse.** Five Ontology Versions (v2 of origin `run`, the rest `registered`), three
Use Case Versions, `production -> v3`, `staging -> v4`. Open `stetiq ui` on the server's
database, or keep `stetiq server` running and use the CLI with a token.

## Files

| File | Role |
| --- | --- |
| `demo.py` | The walkthrough, act by act. `run_demo(http=...)` takes a started server or starts one; returns the state the test reads |
| `scholar_pipeline.py` | The Construction Entry Point: loads the six sources, matches the ORCID sync by name or `--merge-by-orcid` |
| `scholar_graph.py` | `ScholarGraph`, the file-backed stand-in for Neo4j implementing stetiq's `GraphSource` protocol, and the Cypher queries it can answer |
| `scholar_evaluators.py` | `AuthorDedupe`, the custom Construction Run Evaluator the `no-duplicate-authors` Gate reads |
| `stetiq.yaml` | Knowledge Graph name, Entry Point and the six Gates |
| `use-case.yaml` | Use Case Version 1; versions 2 and 3 come from `add_competency_question` in `demo.py` |
| `ontology/` | `v1`, `v3`, and the library's `proposal-venue-hierarchy` and `proposal-rename-cites` |

The local graph file does not run Cypher. It answers the fixed set of query texts in
`use-case.yaml`, `demo.py` and `scholar_evaluators.py` (`scholar_graph.QUERIES`); any
other query fails the question with `UnsupportedQueryError`, which stetiq records by type
name only. Against a real Neo4j, bind the Knowledge Graph to it, set
`STETIQ_GRAPH_SOURCE_URI` and drop the `graph_source=` argument: the Observation and the
custom Evaluator keep running in the SDK process next to the graph credentials, and the
server still only ever sees aggregates.

Two things are left standing on purpose. The `redundancy` Evaluator flags the
`(Paper)-[PUBLISHED_IN]->(Journal)` and `(Conference)` patterns of v4 as implied by the
`Venue` pattern, a judgement call for the team rather than a Gate. And v5, the breaking
rename, stays registered with its failed Gate result: a rejected proposal is part of the
Knowledge Graph's history, not something to delete.
