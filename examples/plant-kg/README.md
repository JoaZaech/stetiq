# Plant maintenance: better by your evals, broken for your Consumer

A factory's maintenance team builds a Knowledge Graph of its work orders, machines,
technicians and parts. Claude reads the technicians' free-text reports; the structured
data comes from the asset register and the maintenance systems' exports. Two Consumers
read the graph: the **reliability dashboard** the morning stand-up triages breakdowns
from, and the **maintenance assistant**, an agent that explains why a machine stopped.

`demo.py` replays three real, recorded Claude rounds from the committed cache in
`llm-cache/`: offline, deterministic, free, with no `claude` CLI and no API key.

```bash
cd examples/plant-kg
uv run python demo.py --reset      # the three rounds (--reset starts over)
uv run python demo.py --reset --epilogue   # ... then hand edits to the graph, and Drift
uv run python demo.py --reset --until v2   # stop with round 2 red: the flywheel step
uv run stetiq ui                   # the same verdicts at http://127.0.0.1:5000/ui
```

## Without stetiq

One pull request changes two things. It brings prompt v2, which also pulls out who
supplied each replacement part, so the maintenance assistant can answer a new question,
"Which suppliers' components keep failing?". And it takes in the export of Line 2's new
maintenance system (an EAM), which since the migration is the system of record for
Line 2's work orders. Every check the team runs passes, so it ships.

But the EAM's order types call a breakdown `corrective`, not `breakdown`, and the
pipeline copies a work order's `kind` from the export, as it always has. The reliability
dashboard counts breakdowns with `kind = 'breakdown'`. Nothing errors: the dashboard
quietly drops Line 2's two breakdowns (CNC-04's worn spindle bearing, Lathe-02's sticking
chuck valve) from the stand-up. Claude read those reports right; the new export's codes
broke the dashboard.

## With stetiq

The demo prints one PR-style line per round (these are the recording's real numbers):

```text
v1          Gate ✅   promoted: production -> v1
prompt v2   Gate ✅   Consumer Gate ❌ (reliability-dashboard ❌ breakdown-technicians 6 → 4, −33%; maintenance-assistant ✅ parts-suppliers new, not compared)   not promoted (Candidate stays at v2)
fix         Gate ✅   Consumer Gate ✅ (maintenance-assistant ✅ parts-suppliers new, not compared; reliability-dashboard ✅)   promoted: production -> v3
```

**1. v1, the baseline.** Prompt v1 on `ontology/v1.yaml`, where `WorkOrder.kind` is a
plain string. Every Gate in `stetiq.yaml` passes: Conformance 1.0, 6 of 6 executed
Competency Questions pass, every work order has a report. `production` stays on v1, and
this run is the baseline every Consumer Gate compares with.

**2. Prompt v2.** First the maintenance assistant's Task gains the Competency Question
`parts-suppliers` (a new Use Case Version), so the pipeline has a reason to add
`Supplier`. The pipeline hands Claude the run context (`Client.run_context`: the
Ontology as a suggestion, the Tasks and Competency Questions, and the latest results).
Claude adds `Supplier` and `SUPPLIED_BY` with a Definition for each, and the evolving run
proposes **Candidate v2**, an additive Ontology Diff. By the evals it is better: 7 of 7
questions pass, `parts-suppliers` returns 5 rows, Conformance stays 1.0, and
`unjustified_additions` is 0 because `parts-suppliers` needs what was added. The front
Gate passes.

The reliability dashboard's Consumer Gate (`triage-rows-hold`: no Competency Question of
*Triage breakdowns* may lose more than 10% of its rows) fails: `breakdown-technicians`
goes from 6 rows to 4, −33%. The verdict names the symptom, not the cause: stetiq never
reads instance values. The maintenance assistant's Consumer Gate passes: `root-causes`
keeps its 8 rows, and `parts-suppliers` was not in the Use Case Version the baseline run
was judged by, so it has no baseline and is reported as new, not compared. Candidate v2
stays unpromoted, like an open red pull request.

**The flywheel step (shown, never required).** Between rounds 2 and 3, a coding agent
works out the fix from what stetiq recorded. See [The flywheel step](#the-flywheel-step)
below. The committed round 3 is what the replay runs, so nobody needs an agent or an API
key to see the story.

**3. The fix.** `ontology/fix.yaml` is v1 plus what Candidate v2 added, with
`WorkOrder.kind` bound to the `WorkOrderKind` Vocabulary {`breakdown`, `preventive`}.
Prompt v2 runs again on it (v3). Claude sees the Vocabulary in the Ontology, and wherever
an export's code is not a Vocabulary Value, the pipeline takes the `kind` Claude read from
the report. The Ontology Diff still classes the binding as breaking, but the
`no-breaking-changes` Gate accepts it on evidence: "binding WorkOrder.kind ->
WorkOrderKind accepted: all observed values are in the Vocabulary". Both Consumer Gates
pass (`breakdown-technicians` is back at 6), and `production` moves to v3.

The demo ends with the CI commands that give the same verdicts in a pipeline's pull
request: `stetiq gate` (the Gates of `stetiq.yaml`) and `stetiq consumer gate` (every
Consumer Gate). `stetiq ui` shows the two Consumers, their Tasks and the recorded
Consumer Gate verdicts.

**Epilogue (`--epilogue`).** Someone edits the graph database by hand: adds `SparePart`
nodes and deletes the done follow-ups. The next Observation records Drift against
`production`: two undeclared Concepts and three count drops past the 25% in
`stetiq.yaml`.

## The flywheel step

Stop the replay with round 2's Consumer Gate red, then let a coding agent read the
[Run Context](../../docs/guide/03-python-sdk.md#the-run-context) through `stetiq mcp`,
the read-only MCP server ([Agents and MCP](../../docs/guide/08-agents-and-mcp.md)):

```bash
cd examples/plant-kg
uv run python demo.py --reset --until v2           # rounds 1 and 2; production stays on v1
claude mcp add stetiq -- uv run stetiq mcp         # from this folder: reads .stetiq/stetiq.db
claude "Why is the reliability dashboard's Consumer Gate red on plant-maintenance, and what would you change?"
```

The agent calls the `run_context` tool (`uv run stetiq context plant-maintenance` prints
the same JSON). With no version it reads `production`'s v1, where `WorkOrder.kind` is a
plain string, and its `last_attempt` is prompt v2's run:

- the reliability dashboard's Consumer Gate failed: Task `triage-breakdowns`, question
  `breakdown-technicians`, 6 → 4 rows (−33.3%, limit −10%);
- the maintenance assistant's passed, with `parts-suppliers` new and not compared;
- the front Gate passed;
- `added`, the Ontology Diff to Candidate v2, is additive: only `Supplier` and
  `SUPPLIED_BY`. Nothing in it touches `kind`: the relabelling is in the data, which
  stetiq never reads. What points at `kind` is the row counts: `downtime-by-kind`, which
  groups work orders by `kind`, went from 2 rows to 3 while `breakdown-technicians`,
  which matches `kind = 'breakdown'`, lost two.

Compare the agent's proposal with the committed round 3, `ontology/fix.yaml`: bind
`WorkOrder.kind` to a Vocabulary {`breakdown`, `preventive`} and keep what Candidate v2
added. A good answer names that, and leaves `Supplier` alone because `parts-suppliers`
needs it. Then `uv run python demo.py --reset` replays all three rounds, the fix included.

`tests/test_example_plant_kg.py` stops the replay after round 2 the same way and calls
the `run_context` tool in-process, so the facts above are pinned without an agent, an
LLM or a network. Those tests skip if the `mcp` extra is not installed; the replay
itself never needs it.

### Recording notes

For the screen recording and the presenter's script:

1. `uv run python demo.py --reset --until v2`. Pause on the prompt v2 line: better by
   the evals, red for the reliability dashboard.
2. In a terminal next to it, `claude mcp add stetiq -- uv run stetiq mcp` (once; `claude
   mcp list` shows it), then ask the question above. Show the agent calling `run_context`
   and quoting `breakdown-technicians` 6 → 4 and the additive diff.
3. Read its proposal out, then open `ontology/fix.yaml` next to it. Say plainly where it
   differs: the agent is shown, not trusted; the committed round 3 is what CI replays.
4. `uv run python demo.py --reset` for the fix round, then `uv run stetiq ui`.

An agent's answer differs from take to take: record a take that proposes the Vocabulary,
and never edit `llm-cache/` or the fix to match an answer.

## Claude and the cache

Each report is one `claude -p` call (model `claude-opus-5-5`) with a JSON schema for the
output, no tools and a replaced system prompt. Answers are cached by prompt version,
model and prompt text. Every committed entry is a real, unedited Claude response that
records its model and recording date.

| Flag | Calls Claude | Cache |
| --- | --- | --- |
| (none) | never | reads `llm-cache/`; a miss is an error: "cache miss, rerun with --record" |
| `--live` | on a miss | the gitignored `.graphdb/llm-cache/` |
| `--record [v1 v2 fix]` | for every report of those rounds (default all) | overwrites `llm-cache/` |

`pipeline.py --round v1|v2|fix` runs one round as the Construction Entry Point of
`stetiq.yaml` (`PLANT_ROUND=v2 uv run stetiq run`), the way a pipeline's CI would. An entry
point process cannot propose Definitions to its run, so there the Concepts Claude adds stay
undocumented.

## The data

| Source | Kind | What it holds |
| --- | --- | --- |
| `data/assets/machines.csv` | structured | The asset register: seven machines on two lines |
| `data/assets/material_flow.json` | structured | Which machine feeds which, as drawn in the line layout |
| `data/cmms/work_orders.csv` | structured | The legacy CMMS export: eight work orders, `kind` `breakdown` or `preventive` |
| `data/cmms/eam_line2_orders.csv` | structured | Line 2's EAM export (from prompt v2's round): its three work orders, order types `corrective` or `preventive` |
| `data/hr/technicians.csv` | structured | Technicians and their badge numbers |
| `data/reports/WO-*.txt`, `WO-2038.eml` | unstructured | The technicians' reports: components, root causes, part suppliers, follow-ups. One is an email |

## Files

| File | Role |
| --- | --- |
| `demo.py` | The three rounds; `run_demo()` returns the state for the test |
| `pipeline.py` | The pipeline: the exports and other structured sources, Claude's extraction, the writer, `--round` |
| `graphdb.py` | `LocalGraph`, a file-backed stand-in for Neo4j implementing stetiq's `GraphSource`, and the Cypher queries it answers |
| `evaluators.py` | `Documented` (Ontology Version) and `ReportCoverage` (Construction Run), both named by Gates |
| `stetiq.yaml` | Knowledge Graph name, Entry Point, Drift thresholds and the Gates |
| `use-case.yaml` | The two Consumers, their Tasks and Consumer Gates, and the Competency Questions |
| `ontology/` | `v1.yaml` and `fix.yaml` |
| `llm-cache/` | The recorded Claude responses |

`uv run pytest tests/test_example_plant_kg.py` replays the demo offline and pins its
verdicts. The local graph store does not run Cypher: it answers the fixed set of queries
in `use-case.yaml` and `evaluators.py` by text (`graphdb.QUERIES`). On a real deployment,
bind the Knowledge Graph to Neo4j, set `STETIQ_GRAPH_SOURCE_URI` and drop the
`graph_source=` argument.
