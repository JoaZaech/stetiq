# City transit: stetiq from the command line, the way CI runs it

The platform team at Lindenhaven Transit keeps a Knowledge Graph of the city's timetable:
GTFS routes, trips, stops and stop times from the planning tool, plus the depots and fare
zones from the operator's other systems. Nobody on the team writes Python against stetiq: the
nightly rebuild and the CI step are shell scripts. Where the plant maintenance example drives
the Python SDK, this one drives stetiq through the `stetiq` CLI alone and shows the exit-code
contract those scripts rely on: `0` success, `1` error, `3` a finding. Everything runs offline
and deterministically over SQLite and a JSON "graph database"; `demo.py` invokes the CLI
in-process and prints the equivalent shell command.

## Run it

```bash
cd examples/transit-network-kg
uv run python demo.py                 # the walkthrough, act by act (--reset to start over)
uv run stetiq ui                      # browse the result at http://127.0.0.1:5000/ui
uv run pytest tests/test_example_transit_network_kg.py   # from the repo root: pins the story
```

The pipeline reads `TRANSIT_FEED_DIR` (the GTFS feed, default `data/gtfs`) and `TRANSIT_GRAPH_FILE`
(the graph database file, default `.graphdb/transit.json`) from the environment: its own settings, not stetiq placeholders.

## The data

| Source | Kind | What it holds |
| --- | --- | --- |
| `data/gtfs/*.txt` | GTFS, June 2026 | 1 agency, 10 routes (3 tram, 7 bus), 47 trips, 68 stops (6 platforms under 3 stations), 420 stop times, 3 service calendars. The exporter spells its optional columns `wheelchairBoarding` and `bikesAllowed` |
| `data/gtfs-2026-09/*.txt` | GTFS, September 2026 | The next timetable: night line N1 withdrawn (9 routes, 45 trips, 410 stop times), `depots.csv` renames North Depot |
| `data/depots.csv` | the depot register | 3 depots and the routes stabled at each |
| `data/fare_zones.json` | the fare system | 3 tariff zones and their stops |

`transit_pipeline.py`, the Construction Entry Point, writes 555 nodes and 1028 relationships from
the June feed. An extra column keeps the feed's spelling until the Declared Ontology names it, so
a Candidate inherits the vendor's camelCase, which the `naming_conventions` Evaluator catches.

## The story

**1. Declare.** `stetiq kg create` makes `ontology/v1.yaml` Ontology Version 1 of
`city-transit` (`production` -> v1); `kg bind-source` binds the Graph Source scope
`database=transit`; `use-case register` registers 7 Competency Questions, judged against v1 at
once: 5 answerable, 1 unanswerable (`accessible-stops`), 1 unmapped. `kg evolution-mode strict`.

**2. Build.** `stetiq run` starts the Entry Point. The feed carries `Stop.wheelchairBoarding`,
`Trip.bikesAllowed` and `PARENT_STATION`, none declared by v1: Conformance 0.926, strict
Evolution Mode fails the run and `stetiq run` **exits 1** (`runs list` shows it `failed`, `runs
get` shows the Entry Point itself exited 0). After `kg evolution-mode evolving` the same run
finishes (exit 0) with **Candidate v2**, an additive `ontology diff 1 2`. `ontology evaluate 2
--evaluator transit_evaluators:NamingConventions` runs the team's Evaluator in the CLI process:
2 violations (the camelCase properties). A human writes `ontology/v3.yaml`, the same Concepts
under proper names, documented: 0 violations, 6 of 7 questions answerable, additive against v1.

**3. Gate and promote.** `stetiq gate --version 2` **exits 3**: 3 of 6 Gates fail
(`graph-conforms`, `names-follow-conventions`, `questions-answerable`). A run consumes v3
(`stetiq run --ontology-version 3`, Conformance 1.000), `stetiq gate --version 3` **exits 0**
with all 6 passing, and the CI user promotes: `alias set production 3 --actor ci-bot`.
`alias log` records who moved what and that the Gates had passed.

**4. Operate.** `stetiq observe` finds no Drift (exit 0). `TRANSIT_FEED_DIR=data/gtfs-2026-09
stetiq run` rebuilds from the September feed (542 nodes, Conformance 1.000) and `gate --run`
passes: losing a route is a 10 % drop, within the 20 % the Gates allow. The next export is cut
short, `calendar.txt` lost the weekend service: the run still conforms perfectly, but `gate
--run` **exits 3** on `no-type-collapses` (Service 3 -> 1, RUNS_ON 45 -> 27). Then someone
deletes 164 StopTime nodes (40 %) straight in the database: `stetiq observe` **exits 3** with
three `count_drop` findings against `production` v3, and `drift list` shows the event.

**5. A broken config.** `gates-broken.yaml` misspells `min_score`: `stetiq gate --config
gates-broken.yaml` **exits 1**, not 3, so CI can tell "a Gate failed" from "the Gates could not
be evaluated". `runs compare` lines up the five runs: Ontology Versions 1, 1, 3, 3, 3; Conformance
0.926, 0.926, 1, 1, 1.

## The transcript

What `demo.py` prints, abridged (`$STETIQ_TRACKING_URI` is set for the session; `stetiq gate
--version 3` prints six `PASS` lines and exits 0):

```console
$ stetiq run --config stetiq.yaml
{"feed": "gtfs", "nodes": 555, "relationships": 1028, "routes": 10, "trips": 47, "stop_times": 420}
Construction Run a23626a29d42… failed (Ontology Version 1)
  Conformance: 0.926
  strict Evolution Mode: new Concepts observed: Stop.wheelchairBoarding, Trip.bikesAllowed, PARENT_STATION
[exit 1]

$ PYTHONPATH=. stetiq ontology evaluate city-transit 2 --evaluator transit_evaluators:NamingConventions
naming_conventions: checked=46  compliance=0.956522  violations=2
  - Stop.wheelchairBoarding [violations]: property name is not snake_case
  - Trip.bikesAllowed [violations]: property name is not snake_case
[exit 0]

$ stetiq observe --config stetiq.yaml
Drift: 3 finding(s) against production (Ontology Version 3)
  count_drop      node_type          StopTime  count dropped from 410 to 246 (-40%)
  count_drop      relationship_type  AT_STOP  count dropped from 410 to 246 (-40%)
  count_drop      relationship_type  HAS_STOP_TIME  count dropped from 410 to 246 (-40%)
[exit 3]
```

## In CI: gate the version the pull request registers, promote on success

```yaml
on: {pull_request: {paths: ["ontology/**", "stetiq.yaml"]}}
jobs:
  gate:
    runs-on: ubuntu-latest
    env:
      STETIQ_TRACKING_URI: https://stetiq.lindenhaven.example
      STETIQ_TOKEN: ${{ secrets.STETIQ_TOKEN }}        # an API Token with edit on city-transit
    steps:
      - uses: actions/checkout@v4
      - run: pip install stetiq
      - run: stetiq ontology register city-transit ontology/v3.yaml | tee version.txt
      - run: PYTHONPATH=. stetiq ontology evaluate city-transit "$(awk '{print $3}' version.txt)" --evaluator transit_evaluators:NamingConventions
      - run: stetiq gate city-transit --version "$(awk '{print $3}' version.txt)"   # exit 3 fails the job
      - if: github.event.pull_request.merged
        run: stetiq alias set city-transit production "$(awk '{print $3}' version.txt)"
```

## Files

| File | Role |
| --- | --- |
| `demo.py` | The walkthrough: each act is a `stetiq` command; `run_demo()` returns every step's exit code and output for the test |
| `transit_pipeline.py` | The Construction Entry Point: loads a GTFS feed, the depot register and the fare zones into the graph database file |
| `transit_graph.py`, `transit_evaluators.py` | `TransitGraph`, the file-backed stand-in for Neo4j implementing stetiq's `GraphSource` protocol, with the Cypher queries it answers; `NamingConventions`, the Ontology Version Evaluator the Gate `names-follow-conventions` reads |
| `stetiq.yaml`, `gates-broken.yaml` | Knowledge Graph name, Entry Point, the Drift limit (`max_count_drop`) and the six Gates; the same Gates with a typo, for act 5 |
| `use-case.yaml`, `ontology/` | The Competency Questions; `v1` (the team's first version) and `v3` (after the Candidate) |

Left standing on purpose: `trips-per-service` keeps its June expectation, so the executed
question fails on every September run (pass ratio 0.8) until the timetable team updates it, a
Use Case decision rather than a Gate; `average-dwell-time` stays unmapped until someone gives
it a query, a Concept mapping or a question mapper.

Custom Evaluators run in the process that calls the CLI, so `--evaluator` needs the folder on
`PYTHONPATH`; only the result reaches the tracking database. The local graph database answers the
fixed queries of `use-case.yaml` by text (`transit_graph.QUERIES`) and nothing else; stetiq
knows no file-backed Graph Source, so `demo.py` hands the CLI this one the way stetiq's own CLI
tests do. On a real deployment, point the pipeline at Neo4j, set `STETIQ_GRAPH_SOURCE_URI` (and
`_USER`, `_PASSWORD`) for `stetiq run`, `observe` and `runs evaluate`, and keep `stetiq.yaml`,
the Use Case and the Gates exactly as they are.
