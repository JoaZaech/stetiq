# The plant assistant: a GraphRAG Consumer that stetiq keeps honest

A separate project that uses stetiq the way a customer would, run live on stage. An
upstream pipeline builds a factory's maintenance Knowledge Graph in Neo4j; a maintenance
assistant answers the shift lead's questions from it as text-to-Cypher, with the
Ontology Version it trusts in Claude's prompt. stetiq runs as a remote server between the
two: the pipeline's CI asks it for the Gates and every Consumer Gate over REST, and the
assistant's Connector guard asks it, in the assistant's own code, whether the next
Ontology Version is safe to take.

[STORY.md](STORY.md) is the story and its running order, beat by beat. This page is how
to run it.

It depends on stetiq as a package (a uv path source to this repo) and uses only stetiq's
public SDK, CLI and REST API. Its data, prompts and recorded Claude extraction rounds
(`llm-cache/`) are copied from [`examples/plant-kg`](../../examples/plant-kg/), which
stays the offline 60-second demo.

## Setup

You need Docker (with compose) and uv. From a clean clone:

```bash
cd frontend && npm ci --silent --no-audit --no-fund && npm run build && cd ..
cd showcase/plant-assistant
cp .env.example .env               # set NEO4J_PASSWORD; change a port if it is taken
docker compose up -d --build --wait
```

The stetiq image ships the built web UI, so the frontend is built first. On macOS,
AirPlay Receiver holds port 5000: set `STETIQ_PORT` in `.env` to a free port (and check
nothing else listens on it, e.g. a `stetiq ui` of your own, since `localhost` then
reaches whichever answers first).

`docker compose up` starts five services:

| Service | What it is |
| --- | --- |
| `graph-candidate` | Neo4j Community: every Construction Run writes here, and stetiq observes it |
| `graph-production` | Neo4j Community: a promoted run is deployed here; the assistant answers from it |
| `stetiq` | `stetiq server` from the repo's Dockerfile built with `SEED=none`: auth on, an empty SQLite tracking database in the `stetiq-data` volume. `stetiq ui` is at `http://localhost:$STETIQ_PORT/ui` |
| `tokens` | One-shot: once the server is up, issues an edit token for `show.py` and a read token for the assistant into `.show/tokens/` (gitignored) |
| `assistant` | The maintenance assistant (FastAPI): its chat page at `http://localhost:$ASSISTANT_PORT/` |

A token cannot be preset in `.env`: the server accepts only tokens it issued, so the
`tokens` service issues them after it starts. Sign in to `stetiq ui` with the one in
`.show/tokens/show`. `show.py` reads that token and the ports and password from `.env`
by itself; any of `STETIQ_TRACKING_URI`, `PLANT_CANDIDATE_URI`, `PLANT_PRODUCTION_URI`,
`PLANT_ASSISTANT_URL`, `NEO4J_USER` and `NEO4J_PASSWORD` set in the environment wins.

The rewind goes through docker compose and stetiq's public CLI only: it removes the
`stetiq` service and its `stetiq-data` volume, starts `stetiq` again on an empty one
with the `tokens` service, which issues new tokens with `stetiq token create`, and
recreates the assistant so it reads its new token. So after a rewind, sign in to
`stetiq ui` again with the new token in `.show/tokens/show`.

`docker compose down -v` removes everything, tokens included; the next `up` issues new
ones.

### Scripted answers, written by hand

Without `ANTHROPIC_API_KEY` in `.env`, the assistant answers the two scripted questions
from `recordings/answers.json` and turns free-form questions off (its chat page says
so), and marks each answer *scripted answer (offline)*. Those answers were **written
by hand, not recorded from Claude**: no API key was
available when the showcase was built. Each was written from the rows its Cypher returns
on the show's production graph, in the style the assistant's prompt asks for, and the
file says so in its `provenance`. The Cypher is real: the assistant runs it on
`graph-production` every time, and the work orders it shows come from those rows. Tell
the audience, or set `ANTHROPIC_API_KEY` so Claude answers live (`claude-sonnet-5-5`).

## Running order

Two screens: the assistant's chat page on the left, `stetiq ui` on the right. A terminal
runs `show.py`, which waits for Enter at each beat: each act, and each scripted question
it asks the assistant.

```bash
uv run python show.py              # the whole show: Acts 0 and 1, the rewind, Acts 0, 2, 3
uv run python show.py --epilogue   # ... then the epilogue: a hand edit, Drift
uv run python show.py --act 2      # lost your place: start at Act 2 (the acts before replay silently)
uv run python show.py --reset      # only rewind stetiq, both graphs and the assistant
uv run python show.py --no-pause   # straight through, no Enter (a rehearsal)
uv run python show.py --live       # extraction calls the claude CLI on a cache miss
```

Before each act `show.py` checks every container; if one is down, it stops and names it,
with the command to start it and the `--act` to go on from:

```text
error: graph-production is down: start it with `docker compose up -d graph-production`, then `uv run python show.py --act 2`
```

### What to say at each beat

The lines below are what a run prints (and what `tests/test_showcase_plant_assistant.py`
pins).

**Act 0, Monday morning.** `v1   Gate ✅   promoted: production -> v1   deployed`.
Banner: *on Ontology v1*. Line 2's breakdowns: CNC-04 (WO-2031), worn spindle bearing;
Lathe-02 (WO-2038), sticking chuck valve; the Cypher filters `kind = 'breakdown'`.
Suppliers: "The graph does not record suppliers". *Say:* this is a normal GraphRAG app.
Its prompt is the Ontology. Hold that thought.

**Act 1, without stetiq.** The guard is off; one pull request (prompt v2, plus Line 2's
new EAM export) passes the pipeline's tests and CD deploys it:
`prompt v2   tests ✅   deployed`. Banner: *on Ontology v2*. The suppliers question
answers now (SKF, Parker, Haas, Watlow, Festo). Then: **"Line 2 had no breakdowns."**,
from the same Cypher as Monday. *Say:* nobody's code is wrong; the EAM calls a breakdown
`corrective`, and the Ontology gave Claude no way to know. The shift lead now believes
CNC-04 is fine. Now rewind.

**Rewind.** stetiq, both graphs and the assistant back to the start, guard on; Act 0
replays without a word.

**Act 2, with stetiq.** The same pull request, and this time its CI asks stetiq:

```text
prompt v2   Gate ✅   Consumer Gate ❌ (maintenance-assistant ❌ breakdown-causes 6 → 4, −33%; reliability-dashboard ❌ breakdown-technicians 6 → 4, −33%)   not promoted (Candidate stays at v2)
```

Banner: *on Ontology v1 · v2 offered: refused (breakdown-causes −33%)*. Both answers
stay Monday's: right about Line 2, and still no suppliers. On the right, `stetiq ui`'s
Use Case › Consumers tab shows both Consumers red. *Say:* every eval got better, and the
front Gate passed; stetiq computed the verdict, the assistant enforced it in its own
code, and nobody read an Ontology Diff. (The Diff from v1 to v2 is additive, so the
Candidate's Consumer impact lists no affected Task: only the Consumer Gate, which runs
the Competency Questions, sees the rows go.)

**Act 3, the fix.** `WorkOrder.kind` bound to the `WorkOrderKind` Vocabulary:

```text
fix   Gate ✅   Consumer Gate ✅   promoted: production -> v3   deployed
    Gate no-breaking-changes: binding WorkOrder.kind -> WorkOrderKind accepted: all observed values are in the Vocabulary
```

Banner: *on Ontology v3 · accepted*, by itself. Both questions answer: Line 2's two
breakdowns, and the suppliers. With `ANTHROPIC_API_KEY` set, take a question from the
audience. *Say:* the Ontology is the contract between the people who build the graph and
the systems that read it; stetiq tells every Consumer whether the next version is safe
for them.

**Epilogue (`--epilogue`, if there is time).** Someone edits `graph-production` by hand:

```text
hand edit: +3 SparePart, −6 done FollowUp   Drift ⚠ against production -> v3 (3 structural, 5 statistical)
    undeclared      SparePart
    undeclared      SparePart.name
    undeclared      SparePart.stock
    count_drop      FollowUp  count dropped from 12 to 6 (-50%)
    count_drop      ASSIGNED_TO  count dropped from 20 to 14 (-30%)
    count_drop      HAS_FOLLOW_UP  count dropped from 12 to 6 (-50%)
    count_drop      (FollowUp)-[ASSIGNED_TO]->(Technician)  count dropped from 12 to 6 (-50%)
    count_drop      (WorkOrder)-[HAS_FOLLOW_UP]->(FollowUp)  count dropped from 12 to 6 (-50%)
```

The Drift event is in `stetiq ui`. *Say:* the same contract that gates a release also
watches the graph after it.

## Tests

`tests/test_showcase_plant_assistant.py` (repo root, `uv run pytest`) runs the whole show
headless: an in-process stetiq server reached over REST with a token, two Neo4j
testcontainers, the assistant's app, and a scripted fake Claude replaying
`recordings/answers.json`. It needs Docker. The compose stack itself is checked by a run
on stage.
