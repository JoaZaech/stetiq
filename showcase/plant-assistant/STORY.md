# The plant assistant: a GraphRAG Consumer that stetiq keeps honest

> The story and running order of the show. The numbers and lines below are what
> `tests/test_showcase_plant_assistant.py` pins; [README.md](README.md) tells how to run
> it on stage.

A separate project that *uses* stetiq, the way a customer would: an upstream pipeline builds
a factory's maintenance Knowledge Graph in Neo4j, and a GraphRAG assistant answers the shift
lead's questions from it. stetiq sits between the two. The show is run live: the extraction
replays recorded Claude rounds, the assistant answers with Claude live, including questions
from the audience.

## The cast

| Who | What it is in the show |
| --- | --- |
| **Upstream pipeline** | Reads the asset register, the maintenance-system exports and the technicians' free-text reports; Claude extracts the reports (replayed from `llm-cache/`). Writes every run to `graph-candidate`. |
| **stetiq** | A remote server (Docker, API token). Records each Construction Run, runs the Gates and every Consumer Gate, holds the Ontology Versions and the `production` Contract Alias. |
| **`deploy.py`** | Stands in for the pipeline's CD: copies a run into `graph-production`. |
| **Maintenance assistant** | The hero Consumer. A GraphRAG app: it fetches the Ontology Version it trusts from stetiq, puts it in Claude's prompt, Claude writes Cypher, `graph-production` runs it, Claude answers from the rows. Every answer shows the Cypher it ran. |
| **Its Connector guard** | Inside the assistant. Polls stetiq every 5 s; when a new Ontology Version is on offer, it asks for the assistant's Consumer Gate verdict and switches only if it passes. The banner says what it decided. |
| **Reliability dashboard** | A second Consumer, declared in `use-case.yaml` only. It shows in `stetiq ui` that verdicts are per Consumer. |

Two screens: the assistant's chat page on the left, `stetiq ui` on the right. `show.py`
in a terminal drives the beats and waits for Enter between them.

## The one cause behind everything

Line 2 has moved to a new maintenance system (an EAM). Its export calls a breakdown
`corrective`, not `breakdown`. The pipeline copies a work order's `kind` from the export, as
it always has. Two of the plant's six breakdowns are on Line 2:

- **WO-2031**, CNC-04: spindle vibration, a worn spindle bearing;
- **WO-2038**, Lathe-02: chuck pressure fault, a sticking chuck valve.

Every eval the pipeline team runs gets *better* with the same pull request. Nothing errors.
The two breakdowns just stop being breakdowns.

## Act 0 — Monday morning (v1)

With the stack up (`docker compose up`), `show.py` runs prompt v1 on `ontology/v1.yaml`, promotes it and deploys it.

- Terminal: `v1   Gate ✅   promoted: production -> v1   deployed`
- Assistant banner: **on Ontology v1**
- Ask: **"Why did Line 2's machines break down?"**
  → CNC-04 (WO-2031): worn spindle bearing. Lathe-02 (WO-2038): sticking chuck valve.
  The Cypher shown filters `kind = 'breakdown'` and finds both.
- Ask: **"Which suppliers' components keep failing?"**
  → "The graph does not record suppliers, so I can't say whose components keep failing."
  Honest: v1 has no `Supplier`.

*Say:* this is a normal GraphRAG app. Its prompt is the Ontology. Hold that thought.

## Act 1 — Without stetiq

The guard is off: the assistant follows whatever is deployed. One pull request lands:
prompt v2, which also pulls out who supplied each replacement part, plus Line 2's EAM export.
The pipeline's tests pass, CD deploys it.

- Terminal: `prompt v2   tests ✅   deployed`
- Assistant banner: **on Ontology v2**
- Ask: **"Which suppliers' components keep failing?"** → it answers now. The new feature works.
- Ask again: **"Why did Line 2's machines break down?"**
  → **"Line 2 had no breakdowns."** Confident, fluent, wrong. The Cypher is identical to
  Monday's. The v2 Ontology says `WorkOrder.kind` is a string and nothing more, so Claude
  had no way to know `corrective` exists.

*Say:* nobody's code is wrong. Claude read every report right. The shift lead now believes
CNC-04 is fine. Now rewind.

## Act 2 — With stetiq (prompt v2 again)

`show.py` rewinds: stetiq's tracking database, both graphs and the assistant start over at v1,
guard on (`show.py --act 2` starts here). The same pull request runs, and this time its
CI asks stetiq.

- Terminal (same numbers as the plant-kg recording):
  `prompt v2   Gate ✅   Consumer Gate ❌ (maintenance-assistant ❌ breakdown-causes 6 → 4, −33%; reliability-dashboard ❌ breakdown-technicians 6 → 4, −33%)   not promoted (Candidate stays at v2)`
- The front Gate passes: every executed question passes, Conformance 1.0, `parts-suppliers` returns
  5 rows, `unjustified_additions` is 0. By every eval it is better.
- The assistant's Consumer Gate (`briefing-rows-hold`: no question of *Brief the shift
  lead on breakdowns* may lose more than 10% of its rows) fails. The verdict names the
  symptom, not a guessed cause: stetiq never reads instance data.
- Assistant banner: **on Ontology v1 · v2 offered: refused (breakdown-causes −33%)**
- Ask: **"Why did Line 2's machines break down?"** → right answer, from `graph-production`,
  still on v1.
- Ask: **"Which suppliers' components keep failing?"** → still "not recorded". The
  assistant gives up the new feature rather than take a version that breaks a Task.
- Right screen: `stetiq ui`, the Use Case › Consumers tab, shows both Consumers red, and
  the Candidate's Consumer impact.

*Say:* stetiq computed the verdict; the assistant enforced it, in its own code. Neither
the pipeline team nor the assistant team had to read an Ontology Diff.

## Act 3 — The fix (v3)

`ontology/fix.yaml` is v1 plus what v2 added, with `WorkOrder.kind` bound to the
`WorkOrderKind` Vocabulary {`breakdown`, `preventive`}. Prompt v2 runs again on it. Where an
export's code is not a Vocabulary Value, the pipeline takes the kind Claude read from the
report.

- Terminal: `fix   Gate ✅   Consumer Gate ✅   promoted: production -> v3   deployed`
- The Ontology Diff still classes the binding as breaking; the `no-breaking-changes` Gate
  accepts it on evidence: "binding WorkOrder.kind -> WorkOrderKind accepted: all observed
  values are in the Vocabulary".
- The banner flips by itself on the guard's next poll (within 5 s; `show.py` asks it to
  poll at once): **on Ontology v3 · accepted**.
- Ask both questions: Line 2's two breakdowns are back, *and* the suppliers answer works.
  The Ontology in Claude's prompt now lists the Vocabulary's values.
- Ask an audience question. Anything about the plant.

*Say:* the Ontology is the contract between the people who build the graph and the systems
that read it. stetiq versions it, evaluates it, and tells every Consumer whether the next
version is safe for them.

## Epilogue (optional)

Someone edits `graph-production` by hand: adds `SparePart` nodes and deletes the done
follow-ups. The next Observation records Drift against `production` in `stetiq ui`
(`show.py --epilogue`):

- Terminal: `hand edit: +3 SparePart, −6 done FollowUp   Drift ⚠ against production -> v3 (3 structural, 3 statistical)`
- Structural: `SparePart`, `SparePart.name` and `SparePart.stock` are undeclared by v3.
- Statistical (beyond `stetiq.yaml`'s `max_count_drop: 0.25`): `FollowUp` 12 → 6,
  `HAS_FOLLOW_UP` 12 → 6, `ASSIGNED_TO` 20 → 14.

## If something goes wrong on stage

- **No Wi-Fi or no `ANTHROPIC_API_KEY`:** the scripted questions answer from recorded
  responses; free-form questions are disabled and the chat page says so.
- **A container is down:** `show.py` checks the stack before every act and says which.
- **Lost your place:** `show.py --act 2` jumps to the start of an act: it rewinds and
  replays the acts before it without a word. `show.py --reset` only rewinds.

## Decisions behind the design

Settled in a grilling session on 2026-11-02.

| # | Decision |
| --- | --- |
| Q1, Q14 | Lives in `showcase/plant-assistant/` in the stetiq repo, built as a separate project: its own `pyproject.toml`, stetiq as a uv path source (a PyPI pin when lifted out), only stetiq's public SDK and REST API. |
| Q2 | Plant-maintenance domain and plant-kg's story; data, prompts and `llm-cache/` copied, not imported. plant-kg stays as it is. |
| Q3, Q13 | Extraction replays recorded Claude rounds (`--live` for real calls). The assistant answers live with the Anthropic API (`claude-sonnet-5-5`), with recorded answers for the scripted questions. |
| Q4, Q15 | Real Neo4j; the pipeline writes it and stetiq's built-in Neo4j Graph Source evaluates it with real Cypher. |
| Q5 | GraphRAG as text-to-Cypher, with the trusted Ontology Version in the prompt. No vector index. |
| Q6, Q12 | `show.py` presenter script; a FastAPI + single-HTML chat page with a version banner and the Cypher of each answer; `stetiq ui` beside it. |
| Q7, Q17 | The assistant has a Connector guard in its own code, built on today's client calls (`get_contract_version`, `latest_candidate`, `get_ontology_yaml`, `list_consumer_gate_results`). It polls every 5 s. No change to stetiq core. |
| Q8 | The assistant gains the Task *Brief the shift lead on breakdowns* (Competency Question `breakdown-causes`, Consumer Gate `briefing-rows-hold`, `row_count_drop` 10%), so v2 hits the hero Consumer. |
| Q9 | The reliability dashboard is declared only. |
| Q10, Q16 | Two Neo4j Community containers, `graph-candidate` and `graph-production`; `deploy.py` copies a promoted run into production (every run, in Act 1). |
| Q11 | The show opens with a without-stetiq act, then rewinds. |
| Q18 | `docker-compose.yml`: two Neo4j, a stetiq server built from the repo's Dockerfile with a build arg that skips the plant-kg seed (SQLite in a volume, API token from `.env`), and the assistant. `show.py` runs on the host. |
| Q19 | A `neo4j`-marked test in `tests/` runs the show headless with recorded answers and pins every verdict and both answers. |
| Q20 | A README for the showcase and a line in the root README; no `docs/guide/` change. |
