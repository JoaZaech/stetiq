# Capability inventory of stetiq as it stands

Wayfinder task [#139](https://github.com/JoaZaech/stetiq/issues/139) for map [#135](https://github.com/JoaZaech/stetiq/issues/135). Facts only: this is the input to the keep/cut/freeze ruling in [#142](https://github.com/JoaZaech/stetiq/issues/142), not a ruling. Terms are from `GLOSSARY.md`. Snapshot: `origin/main` at `6d67cc4` (2026-11-01).

## How the numbers were made

- **LOC** = physical lines (`wc -l`) of git-tracked files on `origin/main`, JSON excluded in `frontend/`.
- **src** = `src/stetiq/**/*.py`. Modules dedicated to an area count whole. The shared tracking stack (`client.py`, `cli.py`, `server.py`, `tracking/service.py`, `sql_store.py`, `remote.py`, `codec.py`, `entities.py`, `store.py`) was split per function by name (e.g. `set_alias`, `list_promotions` → Aliases & Promotion; `create_app`'s nested routes likewise). Glue, imports and unmatched functions stay in *Tracking stack & stores*. Sizes are rough (±20%).
- **frontend** = `frontend/src` non-test code. **tests** = `tests/*.py` + Vitest `*.test.ts`/fixtures + `frontend/e2e` specs and seeds.
- Areas without a dedicated module (Vocabularies, Definitions/Deprecation, Steward/Authority) are spread through the Ontology model, YAML format, Diff, Conformance and Drift; their src figure is a floor.

**Totals on main:** src 12,336 · frontend 18,326 · tests ~22,000 (Python 11,640; Vitest + Playwright ~10,400) · user guide 1,370 (7 pages) · examples 14,499 (incl. data files; ~6,600 of it Python).

**Pipeline side** (per the map's Destination): **front** = the Gate on what the extraction pipeline produced; **back** = the Consumer Gate per Consumer; **versioning** = the Ontology versioning between them; **none** = supporting/infra.

## Summary table

| # | Area | Surfaces | src / frontend / tests LOC | Issues | Pipeline side | Coupling (what breaks if removed) |
|---|---|---|---|---|---|---|
| 1 | Ontology Versions & YAML format (model, canonical hash, dedupe, numbering, Candidates list) | SDK, CLI `ontology register/list/get`, REST `ontology-versions`, UI Ontology Versions list + version page (Overview, Ontology tabs) | 1,186 / 1,507 / 1,120 | #1 #2 #25 | versioning | Everything: every other area keys on an Ontology Version |
| 2 | Ontology Diff (`Change` with breaking/deprecating/cosmetic, field-based) | SDK `diff_ontology_versions`/`diff_ontologies`, CLI `ontology diff`, REST `ontology-diff`, UI Changes tab + Compare page (Table) | 594 / 769 / 976 | #5 #26 #95 #97 #99 | versioning | `ontology_diff` Gate, Consumer impact, Map comparison, Promotion dialog |
| 3 | Ontology Map (node-link view, compare superimposed, path, search, focus) | UI only | 0 / 3,028 / 3,735 | #62–68 #86–89 #91 #102 #109–115 | versioning (view) | Nothing downstream; reads Diff `Change` fields |
| 4 | Ontology Table (Classes, Relations, Attributes grids, links to Map) | UI only | 0 / 424 / 489 | #90 #92–94 #98 | versioning (view) | Shares selection/links with Map |
| 5 | Vocabularies (declare, bind, diff, observe values, check) | SDK/YAML, Diff, Conformance, Drift; UI via Diff + Conformance tab | spread / spread / 364 | #81 #83 #85 | versioning + front | Value reads in Graph Source adapters, Conformance value checks, Drift value findings |
| 6 | Definitions, Alternative Labels, Deprecation (+ reasons), cardinality, `definitions` Evaluator | YAML/SDK, Diff (cosmetic class), Map "documentation-only" level, Evaluator | 65+spread / spread / 146 | #76 #77 #80 #84 #91 #114 | versioning | Diff severities (deprecating/cosmetic), Consumer impact "will be affected" level, Map quiet level |
| 7 | Steward / Authority on a Knowledge Graph | SDK `set_knowledge_graph_governance`, CLI `kg steward/authority`, REST `PUT …/governance`; **no UI** | 77 / 0 / ~30 (in KG tests) | #78 | none (metadata) | Nothing reads it |
| 8 | Aliases, Contract Alias, Promotion & audit log | SDK, CLI `alias set/list/get/log/contract`, REST `aliases`, `promotions`, `contract-alias`; UI Promote dialog, alias chips, Promotions page | 363 / 478 / 384 | #9 #28 #130 | versioning | Contract Alias feeds `start_run` default, `observe` bound Attributes, Drift baseline; audit reads `gate_result` |
| 9 | Construction Runs, run-level evaluation & Construction Entry Point | SDK `start_run`/`ActiveRun`/`run_entry_point`, CLI `run`, `runs list/get/compare/evaluate`, REST `runs`, UI Construction Runs list + run page (Overview, Conformance, Evaluations) | 645 / 1,101 / 1,488 | #4 #13 #15 #29 | front | Conformance, Candidates, run Gates and KPI compare all hang off runs |
| 10 | Run/version KPI charts & compare (metric charts, Evaluator charts, Gate bound lines, drill-down) | UI Run Compare page, run/version chart views | 0 / 1,340 / 822 | #27 #30 #117 #118 #121 #122 | front | Reads Gate Previews (#22); nothing depends on it |
| 11 | Observation & Graph Sources (protocol, in-memory, Observed Schema, `observe`) | SDK `observe`, CLI `observe`, `observations list`, `kg bind-source/source`, REST `observations`, `graph-source`; UI Observations page | 909 / 310 / 659 | #4 #16 #34 | front | Conformance, Candidates, Drift, executed Competency Questions all need an Observed Schema |
| 12 | Neo4j Graph Source adapter | SDK (`STETIQ_GRAPH_SOURCE_URI`) | 314 / 0 / 141 | #7 | front | Only real DB adapter; examples stand in with file-backed graphs over `InMemoryGraphSource` |
| 13 | Conformance, Evolution Mode & Candidates | Inside `end_run`; CLI `kg evolution-mode`, REST `evolution-mode`; UI run Conformance tab | 594 / (in #9) / 444 | #8 | front | `conformance` Gate, Candidates → Promotion |
| 14 | Drift (count/statistical, Vocabulary values) | CLI `observe` exit 3, `drift list`, REST `drift-events`; UI Observations page | 343 / (in #11) / 260 | #16 #34 | front (monitoring) | `count_drop` Gate is separate; nothing else |
| 15 | Evaluator framework & structural built-ins (`hierarchy`, `isolated_node_types`, `orphan_concepts`, `redundancy`, `constraint_consistency`), custom Evaluators | SDK `evaluate`/`register_evaluator`, CLI `ontology evaluate/evaluations`, REST `evaluations`/`evaluate`; UI metric columns | 1,404 / 0 / 356 | #6 #13 | versioning + front | `metric` Gates, KPI charts, every Evaluator below |
| 16 | Gold-ontology alignment Evaluator | SDK (client-side, parameterised) | 87 / 0 / 99 | #11 | versioning | None |
| 17 | Structural answerability & `competency_question_coverage` (traceability) | Built-ins run on register; UI Use Case answerability | 341 / (in #19) / 176 | #10 #79 #82 | back | Task readiness, Consumer impact (shared Concept mapping) |
| 18 | LLM Competency Question mapping (question mapper, optional `llm` extra) | `stetiq server --question-mapper` / env | 189 / 0 / 318 | #12 | back | Concept mappings for #17 and #20 fall back to declared mappings or `unmapped` |
| 19 | Use Cases, Competency Questions, Consumers & Tasks, Task readiness, executed CQs | SDK `register_use_case`/`add_competency_question`, CLI `use-case register/add-question/list/get`, REST `use-case-versions`; UI Use Case page (edit CQs, Consumers, Tasks), Use Case compare | 1,020 / 2,220 / 2,179 | #10 #32 #33 #124 #126 #127 #129 | back | Answerability, coverage, Consumer impact, Planned Consumer cards |
| 20 | Consumer impact of an Ontology Diff | SDK `consumer_impact`, CLI (`ontology diff`), REST `consumer-impact`; UI Diff view + Promotion confirmation | 223 / 293 / 589 | #128 #130 | back + versioning | Promotion dialog |
| 21 | "Planned" placeholders (pipeline strip, Connector / Consumer Gate on Consumer cards, Gate over Consumer impact, AI drafting) + `docs/vision.md`, `docs/specs/consumer-connector.md` | UI only (+ Help vision page) | 0 / 163 / 147 (+338 docs) | #125 #131 | back (shown, not built) | None |
| 22 | Gates (`ontology_diff`, `conformance`, `metric`, `count_drop`) & Gate Previews | CLI `gate` (exit 3), `gate-results`; SDK `evaluate_gates`/`preview_gates`; REST `gate-results`, `gate-previews`; UI latest Gate result, run compare verdicts | 825 / 356 / 886 | #14 #119 #120 #121 | front (+ versioning: diff Gate) | Promotion audit `gate_result`; KPI chart bounds; CI exit-code contract |
| 23 | Server mode, API Tokens, auth, web sign-in/CSRF, `stetiq ui` local mode, `/ui` serving | CLI `server`, `ui`, `token create/list/revoke`; REST `/whoami`, `/auth/sign-in/out`; UI sign-in, Settings | 384 / 338 / 1,715 | #3 #17 #22 #23 #47 | none | Every REST route's `authorize`; remote mode of the SDK; whole web UI |
| 24 | Knowledge Graph registry & navigation (create/list, description, home, switcher) | SDK, CLI `kg create/list/description`, REST `knowledge-graphs`; UI Home, KG list, KG header | 277 / 1,013 / 581 | #2 #24 #31 #52 #54 #55 | none | Root entity of everything |
| 25 | Tracking stack & stores (Protocol, `LocalTrackingService` core, `SqlStore` SQLite/Postgres, codec, wire, remote client, errors, config) | infra | 2,496 / 0 / 475 | #3 #96 #100 #101 | none | Everything |
| 26 | CLI as a surface | `stetiq` Typer app: 8 sub-apps, 39 commands | 1,021 total (split into areas above) / 0 / 548 (general + smoke) | #14 #15 #16 #49 | none | CI usage in examples (transit) relies on exit codes |
| 27 | Web UI shell & shared components (router, layout, sidebar, shadcn `ui/`, data table, theme) | UI | 0 / 4,527 / 468 | #18 #21 #22 #52 | none | Every page |
| 28 | Help / user guide (`docs/guide/` rendered at `/ui/help`, Mermaid) | UI + docs | 0 / 459 / 452 (+1,370 guide) | #44–51 | none | CLAUDE.md rule: every user-visible change updates it; `test_guide_*` checks guide against CLI/YAML |
| 29 | Test infrastructure (`client` fixture over local/remote/Postgres, Playwright harness + seed registry, packaging, CI) | dev | — / — / 558 (+ 72 CI) | #103 #104 #106 | none | All tests |
| 30–35 | Examples (6) | scripts + `stetiq.yaml` + data | see below | #129 (Consumers/Tasks); otherwise no issue | mixed | `tests/test_example_*.py` (1,444 LOC) run them |

### Examples

| Example | Story (README) | py / yaml / data LOC | test LOC | Distinctive |
|---|---|---|---|---|
| `plant-kg` | Factory maintenance, "a complete stetiq walkthrough" | 1,538 / 414 / 114 | 199 | **Only example with an LLM extractor**: `ClaudeExtractor` via `claude -p`, guided by the Declared Ontology, with an LLM cache; rules-v1/v2 fallbacks |
| `clinical-trials-kg` | Hospital trial registry, Ontology as contract | 1,245 / 690 / 1,466 | 252 | strict Evolution Mode, a merge proposal, gold Ontology |
| `retail-orders-kg` | Online retailer, nightly pipeline over a season | 1,215 / 533 / 181 | 290 | synthesised data, run comparison, Drift |
| `citation-graph-kg` | University research output, three teams | 1,074 / 320 / 1,407 | 252 | server mode with API Tokens |
| `transit-network-kg` | GTFS timetable, shell scripts only | 1,050 / 314 / 1,196 | 237 | CLI-only, CI-style, `gates-broken.yaml` |
| `bookshelf-kg` | Two-branch town library, smallest walkthrough | 490 / 333 / 57 | 214 | minimal SDK tour |

`examples/run_all.py` (110) runs all six; `test_example_use_cases.py` (40) checks their Use Cases. No example uses the Neo4j adapter; each ships a local file-backed graph that hands `observe` to stetiq's `InMemoryGraphSource`, naming Neo4j as the production path.

## Notes per area

**1 Ontology Versions & YAML.** `ontology/model.py`, `yaml_format.py`, `canonical.py`, `digest.py`. The content hash is pinned by a golden test; see `docs/architecture.md` › *Layering* (content hashes, schema changes). Candidates are versions with origin `run`.

**2 Ontology Diff.** `ontology/diff.py`. A `Change` states owner/attribute/pattern/vocabulary as fields; UI reads fields, never `detail` (› *Where code runs*, last paragraph). The REST route composes a pure function (› *Adding an operation*).

**3 Ontology Map.** The largest UI area (3,028 code + 3,735 tests, 10 Playwright `ontology-map-*` specs). Pure-TS layout/focus/search/path modules with Vitest tests (#102). Frontend › *Map*, › *Comparison*.

**4 Ontology Table.** Frontend › *Table*. Smaller; shares concept selection with the Map.

**5 Vocabularies.** No module of its own: lives in the model, YAML, Diff (`concept_kind` `vocabulary`), Graph Source value reads capped by `value_cap` (› *Where code runs*), Conformance value mismatches, Candidate extension, Drift value findings.

**6 Definitions / Alt Labels / Deprecation / cardinality.** Spread across model, YAML, Diff (cosmetic and deprecating classes), Conformance (cardinality), Map (documentation-only level, Before/After) and `evaluation/definitions.py`.

**7 Steward / Authority.** Two fields on the Knowledge Graph, set via SDK/CLI/REST. No UI, no Evaluator or Gate reads them.

**8 Aliases & Promotion.** No module of its own (service + store). Promotion audit rows carry the latest `gate_result` and actor (› *Server auth* › Actor). Promotion dialog shows Consumer impact (#130).

**9 Construction Runs & Entry Point.** `entry_point.py` + runs in the shared stack. Run built-ins `conformance`, `observed_schema`, `competency_question_execution` (› *Reserved Evaluator names*). `stetiq run` exit 1 on non-finished (› *Repo config*).

**10 KPI charts & compare.** Frontend only (`runs/compare.ts`, `MetricChartGrid`, `kpi-sheet`, `gate-verdicts`). Arrived with spec #117 (PR #123). Judges ungated runs through Gate Previews (ADR 0007).

**11 Observation & Graph Sources.** `graph_source/` (protocol, model, memory). Observation runs SDK-side; only aggregates leave the process (ADR 0001, ADR 0005; › *Where code runs*).

**12 Neo4j adapter.** `graph_source/neo4j.py`; testcontainer tests marked `neo4j` (› *Testing* › Python). The only real-database adapter, and no example uses it.

**13 Conformance / Evolution Mode / Candidates.** `conformance.py`; all three run inside `end_run` in one transaction. Axioms read closed-world (ADR 0006).

**14 Drift.** `drift.py`; thresholds from `stetiq.yaml` `drift:`; exit code 3 (› *Repo config*). Never registers a version or moves an Alias.

**15 Evaluator framework & structural built-ins.** `evaluation/framework.py`, `structural.py`, `run.py`. Renaming a built-in breaks users' Gates (› *Reserved Evaluator names*).

**16 Gold alignment.** `evaluation/alignment.py`; client-side, used by the clinical-trials example.

**17 Answerability & coverage.** `evaluation/answerability.py`. Both run on every new Ontology Version and every new Use Case Version against the latest Ontology Version; `traced_concept_ratio` is the "traceability" metric (#82). `regressed_questions` (#79).

**18 LLM question mapping.** `evaluation/llm_mapping.py`, Anthropic SDK as optional `llm` extra, server-side only in remote mode. Tests use a scripted `FakeAnthropic`. This is LLM mapping of *questions to Concepts*, not extraction.

**19 Use Cases, CQs, Consumers & Tasks.** `use_case/` (model, format, concepts, cypher, paths, requirements). Consumers and Tasks were added by spec #124 (PR #133). The UI Use Case page is the second-largest UI area.

**20 Consumer impact.** `impact.py`, pure function over a Diff and a Use Case: affected / will be affected / unknown per Task and Consumer. The closest thing on main to a Consumer-side verdict, but it is *not* a Consumer Gate: no Gate kind reads it (the "Gate over Consumer impact" is a Planned placeholder).

**21 Planned placeholders.** `components/Planned.tsx`, `PipelineStrip.tsx`, `use-case/planned.tsx`, `OverviewTab` badge; each links to a section of `docs/vision.md`. **Consumer Gate, Connector, Pending Migration and Adoption are glossary terms with no code on main** (zero hits in `src/`; UI mentions only in placeholders). `docs/specs/consumer-connector.md` (236 lines) specifies the Connector.

**22 Gates & Gate Previews.** `gates.py`; Gate definitions come from the client's `stetiq.yaml`, outcomes are computed and recorded server-side (› *Where code runs* › Gates). Previews never recorded (ADR 0007). Four Gate kinds, all about one Ontology Version or one run; none about a Consumer.

**23 Server mode & auth.** `server.py`, `auth.py`, `ui.py`; ADR 0002, ADR 0003; › *Server auth for new routes*. Heavily tested (`test_server_trust`, `test_server_mode`, `test_api_tokens`, `test_ui`).

**24 Knowledge Graph registry.** Root entity; description editing (#31), home and switcher.

**25 Tracking stack & stores.** › *Layering*, › *Adding an operation*. SQLite and Postgres via one `SqlStore`; no Alembic (`_ADDED_COLUMNS`).

**26 CLI.** One 1,021-line `cli.py`; exit codes 0/1/2/3 are a CI contract (› *Repo config*). `test_guide_cli.py` checks the guide's CLI page against the real commands.

**27 Web UI shell.** Largest frontend bucket (4,527), about 2,900 of which is vendored shadcn `components/ui/`.

**28 Help.** ADR 0004; Frontend › *User guide*. Also bundles `docs/vision.md`.

**29 Test infrastructure.** `tests/conftest.py` parametrises every feature test over local / remote / Postgres (› *Testing* › Python); Playwright seeds registry (› *Testing* › End-to-end); CI runs lint, typecheck, Vitest, build, Playwright, ruff, pyright, pytest.

## What exists only off main

**Nothing.** All three named "off main" items are already on `origin/main`.

| Item | State | Size of what it brought | Merges cleanly? |
|---|---|---|---|
| `origin/spec-117-kpi-compare` (tip `6dcdbb0`, 2026-10-31) | 0 commits ahead of `origin/main`, 80 behind. Merged via PR #123 (2026-10-31). `git diff --stat origin/main...origin/spec-117-kpi-compare` is empty. | PR #123: 36 files, +2,196 / −101. Evaluator charts on the runs chart view, Gate Previews (SDK + REST, ADR 0007), Gate verdicts on run compare, Gate bound lines and pass/fail points, KPI drill-down sheet (areas 10, 22). | Yes, no-op: `git merge-tree --write-tree origin/main origin/spec-117-kpi-compare` returns main's own tree `eaef5b2`. |
| `origin/spec-124-consumers-and-tasks` (tip `3988418`, 2026-11-01) | 0 ahead, 39 behind. Merged via PR #133 (2026-11-01). Empty three-dot diff. | PR #133: 95 files, +5,318 / −336. Consumers and Tasks in the Use Case, their UI editing, Task readiness, Consumer impact (SDK, CLI, Diff view, Promotion), Planned placeholders, `docs/vision.md`, `docs/specs/consumer-connector.md`, Glossary (areas 19, 20, 21). | Yes, no-op: merge-tree returns `eaef5b2`. |
| Uncommitted edits in the main checkout `/Users/joazach/stetiq` | The checkout is on branch `docs/guide-map-round-3` at `859c30a` (2026-10-31), an ancestor of main (merged via PR #134). Modified: `GLOSSARY.md`, `docs/adr/0001-ontology-not-instance-data.md`. Untracked: `docs/adr/0005-…`, `0006-…`, `0007-…` (plus gitignored `examples/plant-kg/.graphdb/` runtime data). | ADR 0001 and ADRs 0005–0007 are **byte-identical** to main's committed copies (added on main by `2a937ac`, 2026-10-31). The Glossary edit (+86/−14: Class, Relation, Attribute, Axiom, Vocabulary, Vocabulary Value, Deprecation, Definition, Alternative Label, Steward, Authority, Consumer, Task, Consumer Gate, Connector, Gate Preview, Pending Migration, Adoption) equals main's Glossary **minus** the *Consumer impact* entry that main added later (`d0e3241`). | Nothing to merge: the working copy is a strict subset of main. Checked read-only (file hashes against the commit, no git command run in that checkout). |

So the freeze in #135's Notes covers no content that is not already on `main`; the "branches" are stale pointers to merged work.
