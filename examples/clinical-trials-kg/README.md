# Clinical trials: a regulated Knowledge Graph in strict Evolution Mode

A self-contained example of using stetiq where the Ontology is a contract: a hospital's
clinical data manager wants a Knowledge Graph of the trial registry (trials, sites,
investigators, pseudonymous participants, interventions, conditions, adverse events,
visits) built from the registry's monthly export. Nothing may enter the graph that the
Ontology did not declare, the Ontology must align with the data standards team's
reference vocabulary, no personal data may ever have a place in it, and only a bot moves
`production`, and only once every Gate passes.

Where the [plant maintenance example](../plant-kg/README.md) lets Construction Runs
discover Concepts and propose Candidates, this one runs in **strict Evolution Mode from
day one**: a run that meets an undeclared column fails, and every Ontology Version is
registered by a human and judged against a **gold** reference before it is promoted.

Everything runs on your laptop, offline and deterministically. The tracking database is
SQLite, the "graph database" is a JSON file, and the two registry exports are generated
once by `trials_data.py` (seed 7) and committed.

## Run it

```bash
cd examples/clinical-trials-kg
uv run python demo.py                 # the whole story, act by act
uv run stetiq ui                      # browse the result at http://127.0.0.1:5000/ui
uv run pytest tests/test_example_clinical_trials_kg.py   # from the repo root: the story as a test
```

`demo.py --reset` starts over. The CLI works on the same tracking database from this
folder (it reads `./stetiq.yaml` and `.stetiq/stetiq.db` by default):

```bash
uv run stetiq runs list trial-registry
uv run stetiq gate-results trial-registry           # every Gate evaluation the story recorded
uv run stetiq ontology diff trial-registry 1 3
uv run stetiq alias log trial-registry              # who moved what, and whether the Gates had passed
uv run stetiq ontology list trial-registry       # v1 to v4, every one registered by a human
```

## The data

Two exports of the same registry, under `data/`, 556 nodes each:

| File | Gives | May (`export-2026-05`) vs June (`export-2026-06`) |
| --- | --- | --- |
| `trials.csv` | 6 `Trial` | June adds `status` |
| `sites.csv`, `trial_sites.csv` | 8 `Site`, `CONDUCTED_AT` | June adds `country` |
| `investigators.csv` | 10 `Investigator`, `LED_BY` | same |
| `interventions.csv` | 11 `Intervention`, each also a `Drug`, `Device` or `Procedure`; `TESTS` | same |
| `conditions.csv` | 6 `Condition` (ICD-10-like codes), `STUDIES` | same |
| `arms.csv`, `participants.csv` | 12 `Arm`, 150 `Participant`, `ENROLLED_AT`, `ASSIGNED_TO` | same |
| `consent.csv` | `CONSENTED_TO` | May is missing 4 participants' rows |
| `adverse_events.csv` | 64 `AdverseEvent`, `REPORTED_IN`, `EXPERIENCED` | same |
| `visits.csv` | 289 `Visit`, `ATTENDED` | June adds `window_days` |

Participants are pseudonymous throughout: a pseudonym, an age band and an enrolment
date. No name, no date of birth, no contact details exist anywhere in the data, and the
Ontology has no place for them (ADR 0001: only aggregates leave the Graph Source).

## The story

**1. Declare.** `ontology/v1.yaml` becomes Ontology Version 1 of the Knowledge Graph
`trial-registry`, with `production` pointing at it, and the Evolution Mode is set to
**strict** before anything is loaded. The data standards team's reference
(`ontology/gold.yaml`) becomes a second Knowledge Graph, `trial-registry-gold`.
`use-case.yaml` names four Consumers: the safety signal agent that screens each export,
the Data Safety Monitoring Board's quarterly review, clinical operations' site monitoring
dashboard and the sponsor's trial portfolio report. Serious events per trial and per arm
serve both the agent and the board; `consent-withdrawals` serves no Task yet. Their Tasks
need eight Competency Questions: six are
answerable by v1, `events-per-arm` needs `Arm`, `ASSIGNED_TO` and `EXPERIENCED`, which
v1 lacks, and `consent-withdrawals` is unmapped (ratio 0.75).

**2. Build.** The loader writes every column of the May export: 556 nodes, 908
relationships. The export has an arm column and links adverse events to participants,
so the Observation shows seven undeclared Concepts (`Arm`, `Arm.code`, `Arm.kind`,
`ASSIGNED_TO`, `EXPERIENCED` and their two patterns; Conformance 0.894) and in strict
mode the run **fails**: status `failed`, no Candidate, `production` still on v1. The
Contract held. The governance path is a human one: the data manager reviews the export,
finds both legitimate, and registers `ontology/v2.yaml`. The Ontology Diff v1 to v2 is
additive (three additions), seven questions are now answerable, and the second run
finishes with Conformance 1.0 and every executed question passing. The custom run
Evaluator `consent_coverage` reports 0.973: four participants have no `CONSENTED_TO`.

**3. Evaluate.** `client.evaluate` on v2 runs the built-in Evaluators, the custom
`pii_free` Evaluator (0 personal-data properties) and `gold_alignment` against
`trial-registry-gold` v1: precision 0.979, recall 0.836, with `Site.country`,
`Visit.window_days`, `Trial.status` and the gold-only sponsor, outcome, body system and
withdrawal Concepts missing. `constraint_consistency` flags one inconsistency, a
uniqueness constraint on the optional `Investigator.orcid`. The Gates in `stetiq.yaml`
fail 3 of 8: `gold-aligned`, `consent-covered` and `consistent-constraints`.

**4. Align.** `ontology/v3.yaml` adds the three properties the June export carries and
drops the bad constraint: still additive from v1. The third run goes through the
Construction Entry Point in `stetiq.yaml`, the way `stetiq run` would, with
`TRIALS_EXPORT=export-2026-06`: Conformance 1.0, consent coverage 1.0. `compare_runs`
lines the three runs up. Gold recall rises to 0.891, all eight Gates pass, the data
manager promotes `staging` and the `cdm-bot` promotes `production` to v3. The audit log
records both actors and that the Gates had passed.

**5. Operate.** An Observation between runs on the untouched graph finds no Drift. Then
the lab switches on its experimental Biomarker feed and the nightly load runs against
`production`: strict mode fails it again (`Biomarker`, `Biomarker.assay`,
`Biomarker.unit`, `MEASURES`), and `production` stays on v3. Finally a pull request's
proposal to replace `Site` with `Centre` and add `Participant.dob` is registered as v4:
the `ontology_diff` Gate rejects the removal as breaking, and `pii_free` rejects the
date of birth.

## Files

| File | Role |
| --- | --- |
| `demo.py` | The walkthrough, act by act. `run_demo()` returns the state for the test |
| `trials_pipeline.py` | The Construction Entry Point: loads one export folder (`TRIALS_EXPORT`) into the graph |
| `trials_graph.py` | `RegistryGraph`, the file-backed stand-in for Neo4j implementing stetiq's `GraphSource` protocol, and the Cypher queries it can answer |
| `trials_evaluators.py` | `PiiFree` (Ontology Version) and `ConsentCoverage` (Construction Run), both named by Gates |
| `trials_data.py` | The deterministic generator of the two committed exports |
| `stetiq.yaml` | Knowledge Graph name, Entry Point, Drift thresholds and the eight Gates |
| `use-case.yaml` | The Consumers, their Tasks and the Competency Questions |
| `ontology/` | `v1`, `v2`, `v3`, `gold` and the breaking `proposal-merge-sites` |

The local graph database file does not run Cypher. It answers the fixed set of queries in
`use-case.yaml` and `trials_evaluators.py` by text (`trials_graph.QUERIES`); any other
query fails the question with `UnsupportedQueryError`, which stetiq records by type name
only. Against a real Neo4j, bind the Knowledge Graph to it, set
`STETIQ_GRAPH_SOURCE_URI` and drop the `graph_source=` argument: the loader, the Use
Case, the Evaluators and the Gates stay as they are, and strict mode keeps doing its job
against the real database.

Three things are left standing on purpose. `consent-withdrawals` stays unmapped until
the registry exports withdrawals (gold's `WITHDREW_FROM`) and someone gives it a query.
The gold reference keeps `Sponsor`, `Condition.system` and `AdverseEvent.outcome` the
registry does not populate yet, so recall stays below 1.0 and the team can see what the
standard still asks for. And the `redundancy` Evaluator notes that the `TESTS` patterns
on `Drug`, `Device` and `Procedure` are implied by the one on `Intervention`; the
loader labels each intervention with both, as Neo4j models a hierarchy, so the patterns
are declared for the Observed Schema to conform, and that is a judgement call, not a
Gate.
