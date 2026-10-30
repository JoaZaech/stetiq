# Plant maintenance: a complete stetiq walkthrough

A self-contained example of using stetiq the way a team would: a maintenance lead at a
factory wants a Knowledge Graph of the plant's work orders, machines, technicians and
parts, built from the data the plant already has. stetiq versions the graph's
Ontology, judges every build against the lead's Competency Questions, gates changes in
CI and watches the live graph for Drift.

Everything runs on your laptop. The tracking database is SQLite, the "graph database"
is a JSON file, and the technicians' reports are read either by Claude (through the
Claude Code CLI) or by a regex script, so the example also works offline.

```bash
cd examples/plant-kg
uv run python demo.py                 # Claude reads the reports (needs the `claude` CLI, signed in)
uv run python demo.py --extractor rules   # fully offline, deterministic
uv run stetiq ui                      # browse the result at http://127.0.0.1:5000/ui
```

`demo.py --reset` starts over. `uv run pytest tests/test_example_plant_kg.py` runs the
offline story as a test and pins its outcomes. The CLI works on the same tracking database
from this folder (it reads `./stetiq.yaml` and `.stetiq/stetiq.db` by default):

```bash
uv run stetiq runs list plant-maintenance
uv run stetiq gate-results plant-maintenance        # every Gate evaluation the story recorded
uv run stetiq gate plant-maintenance --run <id>     # gate the nightly run again: all nine pass
uv run stetiq ontology diff plant-maintenance 1 3
uv run stetiq alias log plant-maintenance
uv run stetiq drift list plant-maintenance
```

`stetiq gate plant-maintenance --version 3` at the end of the story fails two Gates, and
that is correct: a version is gated with the latest run that consumed it, which by then is
the deliberate strict-mode failure with its `Sensor` nodes.

## The data

| Source | Kind | What it holds |
| --- | --- | --- |
| `data/assets/machines.csv` | structured | The asset register: seven machines, their model and line |
| `data/assets/material_flow.json` | structured | Which machine feeds which, as drawn in the line layout. Stale: the January re-route is missing |
| `data/cmms/work_orders.csv` | structured | Eight work orders from the CMMS, with a `downtime_minutes` column nobody told the ontology about |
| `data/hr/technicians.csv` | structured | Technicians and their badge numbers |
| `data/reports/WO-*.txt`, `WO-2038.eml` | unstructured | The technicians' free-text reports: components, root causes, replacement parts and their suppliers, follow-ups. One is an email |

The structured sources load deterministically. The reports go through an extractor
(`pipeline.py`):

- **rules-v1**, the plant's original regex script: reads the header line, the components and
  the follow-ups. Cannot read the email, ignores causes and suppliers, and trusts the stale
  layout file for material flow.
- **rules-v2**, the script after a fix round. The offline stand-in for Claude.
- **claude**: one `claude -p` call per report, with the Declared Ontology stetiq hands the run in
  the prompt, a JSON schema for the output, no tools and a replaced system prompt. The
  example model is `claude-opus-5-5` (`--model` or `PLANT_EXTRACTION_MODEL` to change it).
  Results are cached in `.graphdb/llm-cache/` by model, ontology and report, so re-running the
  demo or the nightly rebuild costs nothing. Expect about eight calls per fresh walkthrough.

Every extractor returns the same shape (nodes keyed by label and key, plus relationships),
and the writer gives each property the type the Declared Ontology declares (a `DATE` string
becomes a date, an `INTEGER` a number).

## The story

**1. Declare.** `ontology/initial.yaml` becomes Ontology Version 1 of the Knowledge Graph
`plant-maintenance`, with `production` pointing at it. `use-case.yaml` holds the lead's eight
Competency Questions: some with a Cypher query, one with an explicit Concept mapping, one with
neither. stetiq judges them structurally against v1 at once: five are answerable, two need
Concepts v1 lacks (`Fault`, `WorkOrder.downtime_minutes`), one is unmapped. The architecture
team's reference ontology (`ontology/gold.yaml`) becomes a second Knowledge Graph,
`plant-gold`.

**2. Build.** The first Construction Run uses rules-v1 inside `client.start_run`, logging its
params and metrics. stetiq observes the graph and finds three Conformance mismatches: the
required `Technician.badge` is filled on a third of technicians, `WorkOrder.downtime_minutes`
is undeclared (so evolving mode registers **Candidate v2**), and `SUPPLIED_BY` is declared but
never observed. Executing the questions shows two failures: the blast-radius question returns
the stale layout's answer, and the root-cause question returns nothing. The custom run
Evaluator `report_coverage` reports one work order without a readable report (the email).

**3. Evaluate.** `client.evaluate` on the Candidate runs the built-in Evaluators again, the
custom `documented` Evaluator, and `gold_alignment` against `plant-gold`: one orphan
relationship type, one constraint inconsistency (uniqueness on an optional property), nine
undocumented Concepts, recall 0.74 against gold. The Gates in `stetiq.yaml` reject the
Candidate, 7 of 9 failing.

**4. Improve.** `ontology/revised.yaml` adopts the Candidate's discovery, adds `Fault` and
`Supplier` with their patterns, relaxes the badge, drops the bad constraint and documents
everything: v3, an additive change from v1. A ninth question is added with
`add_competency_question` (Use Case Version 2). The second run reads the reports with Claude
(or rules-v2) and reaches Conformance 1.0 with every executed question passing. A nightly
rebuild goes through the Construction Entry Point in `stetiq.yaml`, the way `stetiq run`
would. `compare_runs` lines the three runs up. Gold recall rises to 0.89. All nine Gates
pass, the engineer promotes `staging` and the CI user promotes `production`, and the audit
log records who moved what, and that the Gates had passed.

**5. Operate.** An Observation between runs finds no Drift. Then a fix script adds
`SparePart` nodes straight into the database and deletes the done follow-ups: the next
Observation raises a Drift event with two undeclared Concepts and three count drops beyond
the configured 25 %. In strict Evolution Mode, a run that switches on experimental `Sensor`
nodes is failed instead of yielding a Candidate. Finally a pull request's proposal to rename
`WorkOrder` is registered as v4 and the Gates reject it as breaking; `production` stays on v3.

## Files

| File | Role |
| --- | --- |
| `demo.py` | The walkthrough, act by act. `run_demo()` returns the state for the test |
| `pipeline.py` | The Construction Entry Point: structured loaders, the three extractors, the writer |
| `graphdb.py` | `LocalGraph`, the file-backed stand-in for Neo4j implementing stetiq's `GraphSource` protocol, and the Cypher queries it can answer |
| `evaluators.py` | `Documented` (Ontology Version) and `ReportCoverage` (Construction Run), both named by Gates |
| `stetiq.yaml` | Knowledge Graph name, Entry Point, Drift thresholds and the nine Gates |
| `use-case.yaml` | The Competency Questions |
| `ontology/` | `initial`, `revised`, `gold` and the breaking `proposal-rename-work-order` |

The local graph store does not run Cypher. It answers the fixed set of queries in
`use-case.yaml` and `evaluators.py` by text (`graphdb.QUERIES`); any other query fails the
question with `UnsupportedQueryError`, which stetiq records by type name only. On a real
deployment, bind the Knowledge Graph to Neo4j, set `STETIQ_GRAPH_SOURCE_URI` and drop the
`graph_source=` argument: the pipeline, the Use Case and the Gates stay as they are.

Two findings are left standing on purpose. The `redundancy` Evaluator flags `Line`,
`Component` and `Supplier` as having the same structure (each is just a `name`), which is a
judgement call for the team, not a Gate. And `repeat-faults` stays unmapped until someone
gives it a query, a Concept mapping, or a question mapper (`STETIQ_QUESTION_MAPPER`).
