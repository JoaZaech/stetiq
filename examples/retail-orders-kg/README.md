# Retail orders: operating stetiq over a season

A self-contained example of using stetiq the way an operations team would: the analytics
team of an online retailer keeps a Knowledge Graph of customers, orders, products,
suppliers, warehouses and shipments, built nightly by a pipeline from the order database.
stetiq versions the graph's Ontology, compares the pipeline's Construction Runs, gates
changes in CI and, once a week, observes the live graph for Drift. Where the plant
maintenance example is small and about *building* a graph from messy sources, this one is
large (about 13,000 nodes at season start, 38,000 at the end) and about *running* one:
many runs compared, Observations outside any run, statistical and structural Drift.

Everything runs on your laptop in a couple of seconds, offline and deterministic: SQLite
for tracking, stetiq's `InMemoryGraphSource` as the graph database (kept alive and mutated
between Observations), data generated from `random.Random(2026)` and a few committed seeds.

## Run it

```bash
cd examples/retail-orders-kg
uv run python demo.py                 # the whole season, about two seconds
uv run stetiq ui                      # browse the result at http://127.0.0.1:5000/ui
uv run pytest tests/test_example_retail_orders_kg.py   # from the repo root: pins the story
```

`demo.py --reset` starts over. The CLI works on the same tracking database from this folder
(it reads `./stetiq.yaml` and `.stetiq/stetiq.db` by default); `demo.py` prints the run ids
these commands take:

```bash
uv run stetiq runs compare <run-1> <run-2> ... <run-6>   # the six build runs side by side
uv run stetiq gate retail-orders --run <week-6 run>    # exit 3: three Gates fail (see below)
uv run stetiq drift list retail-orders                 # three Drift events: weeks 4, 5 and 6
uv run stetiq alias log retail-orders                  # who promoted what, with the Gate verdict
uv run stetiq observe retail-orders                    # exit 3 on Drift; needs a live Graph Source (below)
```

Gating the week-6 run again at the end of the story fails three Gates, not the two the demo
showed in week 6, and that is correct: a run is always diffed against the *current* Contract
Alias, and with `production` on v4 the run's v3 lacks `Bin` and `STORED_IN`, a breaking diff.

The weekly Observations the demo takes with `client.observe` are what a cron job would do
with `stetiq observe` (it reads the `drift:` thresholds from `stetiq.yaml`, prints the
findings and exits 3 on Drift, 1 on an error, so a scheduler can tell the two apart). Here it
exits 1: the in-memory Graph Source lives only inside `demo.py`, so there is nothing for the
CLI to observe once the demo has finished; on Neo4j, `STETIQ_GRAPH_SOURCE_URI` points it there.

## The data

| Source | What it holds |
| --- | --- |
| `data/categories.yaml` | The category tree: 6 departments, 12 categories, 28 subcategories (depth 3) |
| `data/products.csv` | 60 products with SKU, subcategory, supplier, price and weight (a few weights missing) |
| `data/suppliers.csv`, `data/warehouses.csv` | 12 suppliers, 5 warehouses |
| `data/calendar.json` | The eight weeks of the season: growth per week, and what else happens to the graph |
| `retail_synth.py` | Generates the rest at demo time: 1,000 customers plus 100 duplicate feed rows, 2,800 orders with 6,375 lines, 2,518 shipments, 331 returns, then each week's new orders |

Every node carries the label `Retail` besides its own, and the Knowledge Graph's Graph
Source is bound to `GraphSourceScope(database="retail", label="Retail")`. Three `Audit`
nodes another team keeps in the same database lack the label: they are outside the scope and
appear in no Observation. On Neo4j the same scope means `MATCH (n:Retail)`.

## The story

**1. Declare.** `ontology/v1.yaml` becomes Ontology Version 1 of `retail-orders`: 9 node
types (`Department` is a child of `Category`, so the hierarchy has depth 2) and 8
relationship types, with `production` pointing at it. `use-case.yaml` holds the analytics
team's 8 Competency Questions: revenue by department, lines per order, suppliers two hops
behind the orders, the category tree's depth with `expected_answer: 3`, and so on. Judged
structurally against v1: 6 are answerable, `return-rate-per-product` needs `Return` and
`RETURNED`, which v1 lacks, and `basket-affinity` is unmapped (ratio 0.750).

**2. Build.** The pipeline runs six times inside `client.start_run`, each run rebuilding the
scope with different params and logging `customers`, `duplicate_customers_merged`, `orders`,
`order_lines` and `build_seconds`. Run 1 runs the orders loader only: `Shipment` and its
relationships are absent, Conformance 0.831, two executed questions fail. Runs 2 and 3 keep
or exact-merge duplicate customers: the guest checkouts have no email, so the required
`Customer.email` is filled on 96 % and Conformance is 0.983. Run 4's fuzzy dedupe merges
them: 1.000. Run 5 switches returns on and observes `Return` and `RETURNED`, which v1 never
declared: Conformance 0.894, and evolving mode registers **Candidate v2**.
`client.latest_candidate` and the Ontology Diff show two additive changes. Mara adopts the
Candidate as `ontology/v3.yaml` with descriptions. Registering it yields **v3**, not v2,
because descriptions are part of an Ontology Version's content hash: only byte-identical
structure is a dedupe hit. Run 6 consumes v3 and reaches 1.000 with all 7 executed questions
passing. `compare_runs` lines the six up (params, metrics, Conformance, pass ratio, node
counts); the best Conformance, 1.000, belongs to runs 4 and 6. The same table shows the
fuzzy runs merging 206 rows for 100 real duplicates, because 106 different people share a
name and a postcode: Conformance is about structure and cannot see that.

**3. Gate and promote.** The seven Gates in `stetiq.yaml` run on v3 against run 6: the diff
from v1 is additive, Conformance 1.000, no type count dropped since run 5, mean fill rate
0.998, hierarchy depth 2, no duplicate-structure Concepts, answerability 0.875. All pass;
Mara promotes `staging`, the CI user promotes `production`, and the audit log records both
with the Gate verdict.

**4. Operate.** Evolution Mode is set to *strict* for the season, so a nightly run that meets
new Concepts fails instead of registering a Candidate. Then eight weekly Observations, with
`max_count_drop: 0.25` and `max_count_increase: 1.5` from `stetiq.yaml`:

| Week | What happens | Observation |
| --- | --- | --- |
| 1 | Season start, 13,047 nodes | no Drift |
| 2, 3 | +6 % orders each | no Drift |
| 4 | Flash sale: +5,191 orders (+165 %), half not shipped yet | **statistical Drift**: `count_increase` on `Order`, `OrderLine`, `PLACED`, `CONTAINS`, `OF_PRODUCT` |
| 5 | The warehouse team's migration adds 120 `Bin` nodes and `STORED_IN` | **structural Drift**: `Bin`, its three properties and `STORED_IN` undeclared |
| 6 | A retention job deletes 60 % of the Shipments in two batches | **both**: the Bins again, plus `count_drop` on `Shipment`, `FULFILLS`, `SHIPPED_FROM` (5,733 to 3,975) |
| 7 | `ontology/v4.yaml` declares `Bin` and `STORED_IN`; a run under v4 passes every Gate; `production` moves to v4 | no Drift |
| 8 | +5 % orders | no Drift |

In week 6 the nightly Construction Run, taken after the second batch, *fails* in strict mode
over the undeclared Bins (Conformance 0.917), and `stetiq gate --run` on it fails two Gates:
`graph-conforms` and `no-type-collapses` (Shipments 3,975 to 2,465, a 38 % drop against the
Observation before it). Drift never created an Ontology Version: v4 is registered by hand,
and the season ends with three Drift events, all measured against `production -> v3`.

**5. Cost at scale.** The last Observation describes 37,678 nodes and 62,852 relationships as
11 node types, 10 relationship types and 11 patterns with counts, fill rates and degrees. The
size of the graph changes how long the Graph Source takes to answer, not what stetiq stores:
the tracking database holds no customer, order or product, which the test verifies by looking
for a generated email address in the SQLite file.

## Files

| File | Role |
| --- | --- |
| `demo.py` | The walkthrough, act by act. `run_demo()` returns the state for the test |
| `retail_synth.py` | The seeds (`data/`) and the deterministic generator of customers, orders, lines, shipments and returns |
| `retail_graph.py` | `RetailGraph`, the pipeline's target and stetiq's Graph Source: the label-scoped `InMemoryGraphSource`, the dedupe strategies, the season's mutations and the canned Competency Question answers |
| `stetiq.yaml` | Knowledge Graph name, Drift thresholds and the seven Gates |
| `use-case.yaml` | The Competency Questions |
| `ontology/` | `v1` (declared), `v3` (the adopted Candidate with descriptions), `v4` (the Bins). v2 is the Candidate the run registered |

Two findings are left standing on purpose. The `redundancy` Evaluator reports the pattern
`(Category)-[SUBCATEGORY_OF]->(Department)` as implied by the one on `Category`; it is
declared anyway because the Observed Schema reports a department under both of its labels,
and leaving it out would be a pattern mismatch in every run. And `basket-affinity` stays
unmapped until someone gives it a query, a Concept mapping or a question mapper.

The in-memory Graph Source does not run Cypher: it answers the query strings of
`use-case.yaml` with aggregates computed from its rows (`retail_graph.py`), and any other
query fails the question by exception type only. Against a real graph database, bind the Knowledge
Graph to Neo4j with the same label scope, set `STETIQ_GRAPH_SOURCE_URI` and drop the
`graph_source=` argument; put the pipeline command under `entry_point:` in `stetiq.yaml` so
`stetiq run` starts the nightly run, and schedule `stetiq observe` for the weekly Observation.
