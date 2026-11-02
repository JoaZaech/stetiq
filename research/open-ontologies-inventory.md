# Open Ontologies: inventory of capabilities, mapped to stetiq

Research for [#198](https://github.com/JoaZaech/stetiq/issues/198), part of the wayfinder map [#197](https://github.com/JoaZaech/stetiq/issues/197). Every fact about Open Ontologies (OO) below comes from its repository, not from memory.

- **Source:** [fabio-rovai/open-ontologies](https://github.com/fabio-rovai/open-ontologies) at `main` = `9af00fa` (2026-11-02). Read: `README.md`, `CLAUDE.md`, `docs/tool-reference.md`, `docs/lifecycle.md`, `docs/architecture.md`, `docs/ci-gates.md`, `docs/modules-and-conservativity.md`, `docs/alignment.md`, `docs/decisions/` (README plus the records it indexes).
- **Source code, read only to settle an ambiguity:** `src/plan.rs`, `src/monitor.rs`, `src/drift.rs`, `src/lineage.rs`, `src/policy.rs`, `src/server.rs` (tool attributes), `src/main.rs` (`serve-http`).
- **Marking:** a claim taken from source code and not from the docs ends in **[src]**. Unmarked claims are from the docs. Where the docs and the code disagree, both are given.
- **stetiq side:** `GLOSSARY.md`, ADR 0001, 0005, 0006, 0007, `docs/architecture.md` › *Where code runs* and › *Server auth for new routes*, `docs/vision.md` › *AI and MCP authoring*.

## What Open Ontologies is, in one paragraph

A single Rust binary (Oxigraph triple store, SQLite state, Lean 4 checkers) that loads RDF/OWL **and instance data** into an in-process store, reasons over it (RDFS, OWL-RL, a SHIQ tableaux), and changes that store through a Terraform-style loop: `plan` → `apply` → `monitor` → `drift` → `rollback`. Its differentiator is evidence: each derived triple can carry a certificate that a proved-sound Lean checker re-verifies. It exposes 124 tools over MCP (stdio, streamable HTTP, a Unix socket), plus a CLI, a batch runner and a desktop Studio. The README says outright: "This is not an ontology editor… You run Open Ontologies on the change, before the change goes to production."

The basic split from stetiq: **OO governs one RDF store, TBox and ABox together, open-world, with a reasoner, and it writes to that store. stetiq governs Ontology Versions only, closed-world, with no reasoner, and never writes to (or, from the core, connects to) a graph database.** Nearly every OO lifecycle capability does its work *on the store*, so it hits ADR 0001, 0005 or 0006 as soon as it is taken literally. The adoptable parts are the *ideas* behind a report, not the mechanism.

## Read first: the four capabilities ruled first

### 1. `plan`: blast radius, risk score, locked IRIs, conservativity, logic

What a plan is (`docs/lifecycle.md` › *Plan*; `src/plan.rs`):

- **Input.** The proposed Turtle is the *complete desired state* of the store, as in Terraform. Anything absent from it is removed, **instance data included**. The plan therefore reports added and removed classes, properties *and individuals*, plus the triple-level insert/delete counts.
- **Persistence.** Every plan is stored in SQLite with a `plan_id`, so `plan` and `apply` can be separate calls. The 100 most recent are kept. "Most recent" is scoped to the MCP session or the CLI, so one session cannot apply a plan another is still reviewing.
- **Blast radius** = the number of triples in the *current store* that mention any removed class, property or individual IRI, as subject, predicate or object. It is a single integer, `blast_radius.triples_affected`, computed with one SPARQL `COUNT` per removed IRI **[src]**. It counts instance triples, not downstream users. No Consumer, query or application enters it.
- **Risk score** (`low`/`medium`/`high`) is a fixed rule **[src]**:
  - `high` if anything is removed *and* `triples_affected > 0`;
  - `medium` if something is removed but nothing refers to it;
  - `low` otherwise (additions only);
  - raised to `high` by the `logic` block (below) when the change adds an error- or warning-severity TBox defect, or makes the ABox inconsistent where the store was not proven inconsistent.
  - `risk_reasons` lists one sentence per cause.
  - There are no weights, no thresholds, and no configuration.
- **Locked IRIs.** `onto_lock` writes an IRI and a reason to an `iri_locks` table. A plan that removes a locked **class or property** lists it under `locked_violations` and adds a sentence to `risk_reasons`. Locks are **reported, not enforced**: the risk score is not changed by a lock **[src]**, and `apply` never reads the lock table **[src]**. Individuals are not checked against locks **[src]**. The tool text ("Lock IRIs to prevent removal during plan/apply") promises more than the code does.
- **Conservativity block** (`docs/modules-and-conservativity.md`): it reasons the store and store+change to a fixpoint under a Horn rule table (RDFS/OWL-RL), then reports every *new consequence over names the store already used*, each with the rule and the premise the base lacked. The headline example: adding one `rdfs:domain` triple adds nothing, removes nothing, has blast radius 0, scores `low`, and retypes 901 existing individuals. The verdict is a word (`conservative_under_rule_table`, `not_conservative_under_rule_table`, three `undecided_*` words), never a bare boolean. It is "a finding, not an error". It is on by default over MCP and CLI and costs a fixpoint over both graphs. (The Rust API `Planner::plan()` leaves it off; the tool and CLI turn it on **[src]**.)
- **Logic block** (#336): new TBox self-defects (eight kinds: subclass cycles, disjoint with an ancestor, transitive+functional…) the store did not have, and ABox consistency of the proposed graph by the SHIQ tableaux. Three-valued: `null` when the reasoner budget ran out, never a false `true`.
- **Not a gate.** `plan` exits 0 whatever the score. "A pipeline gates on `risk_score` or `logic`." `apply` does not re-judge the plan.

**Mapped to stetiq.**

| OO part | Nearest stetiq concept | ADR? | Ticket |
|---|---|---|---|
| Plan as a diff of current vs proposed | **Ontology Diff** between the Contract Alias's version and a **Candidate**. stetiq's diff is per Concept and classed cosmetic/additive/deprecating/breaking; OO's is per IRI and per triple, and not classed. | Diffing *individuals* needs 0001. The Ontology-only diff does not. | change planning (#199) |
| Persisted plan, applied later by id | A **Candidate** is already a persisted, immutable proposal; **Promotion** is the "apply". | none | #199 |
| Blast radius = instance triples that mention removed terms | **Consumer impact** is stetiq's blast radius (the glossary lists "blast radius" under *Avoid*): changed Concept → Competency Questions → Tasks → Consumers. The closest *instance-count* analogue is the **Observed Schema** counts per class and relation, which could weight a removal by "how many nodes/edges of this Class the graph holds". | Counting triples in the live store needs 0005 (core never connects) and touches 0001. Weighting by Observed Schema aggregates does not. | #199 |
| Risk score low/medium/high | **Ontology Diff** classification (additive/deprecating/breaking) plus Consumer impact levels (affected / will be affected / unknown). A **Gate** over the diff is how a user turns either into a CI verdict. | none | #199 |
| Locked IRIs | No direct concept. Nearest: a **Gate** over the Ontology Diff ("no breaking change to Concept X"), or a Concept a **Consumer**'s Task depends on (which already makes its removal *affected* in Consumer impact). | none | #199 |
| Conservativity (new entailments over old names) | None. Under ADR 0006 an Axiom never derives facts, so "a new consequence" has no meaning in stetiq. The *closed-world* analogue already exists: ADR 0006 makes adding or tightening an Axiom a **breaking** Ontology Diff change, because existing graphs may stop conforming. | **0006** (needs a reasoner and open-world reading) | #199 (pitch contrast) |
| Logic block: new TBox defects | Version built-in Evaluators (`hierarchy`, `constraint_consistency`, `orphan_concepts`, …) and a **Gate** over their delta. | Defect *kinds* are fine; ABox consistency needs **0001** and **0006**. | #199 |

### 2. The lifecycle: apply, monitor, drift, rollback, lineage

(`docs/lifecycle.md`; `src/plan.rs`, `src/monitor.rs`, `src/drift.rs`, `src/lineage.rs`)

| Capability | What it does | Nearest stetiq concept | ADR? | Ticket |
|---|---|---|---|---|
| `onto_apply` `safe` / `force` | Writes the plan's triple delta into the store (or clears and reloads when blank nodes are present). Instance triples go too. `safe` refuses only when a monitor watcher has set the *blocked* flag; `force` ignores that. Risk score, logic and locks are not checked. | **Promotion** (moving the Contract Alias). stetiq "deploys" by moving a pointer and the user migrates the graph (ADR 0001 and 0005 › Consequences). | Writing the graph: **0001** and **0005** | audit and evidence (#201); apply semantics also matter to #199 |
| `onto_apply` `migrate` | Same, plus for each removed term paired (one-to-one, Jaro-Winkler similarity ≥ 0.6) with an added one: an `owl:equivalentClass`/`equivalentProperty` bridge, `owl:deprecated true` and a "Deprecated: migrated to X" comment on the old term **[src for the deprecation triples]**. Bridges are reported with their score; declined removals are listed. | **Deprecation** with a named replacement, and the glossary's "a rename is a removal plus an addition unless declared as a replacement". OO *guesses* the replacement; stetiq has the user declare it. | Equivalence bridges are OWL inference: **0006** for their semantics. A rename *suggestion* in the diff needs no ADR. | #199 |
| `onto_monitor` and the background loop | User-registered SPARQL `SELECT ?count` watchers with a threshold. On breach: `notify` (optional webhook POST), `block_next_apply` (sets a flag `apply safe` checks), `auto_rollback` (restores the most recent saved version snapshot into the store), or `log`. `serve-http`/the daemon can run them on an interval. Only `check_type: "sparql"` is evaluated; any other type returns 0 and passes **[src]**. | **Observation** + **Drift** thresholds (`drift:` in `stetiq.yaml`), run by the user's scheduler (ADR 0005: monitoring "is not a stetiq component"). A planned **Consumer Gate** on each Observation is the nearest counterpart to `block_next_apply`. | Running queries against the graph from the core, a scheduler in the server, and rolling back the store: **0005**, **0001** | #201 |
| `onto_drift` | Compares two ontology files: added/removed IRIs, likely renames (Jaro-Winkler on labels/local names, self-calibrating threshold from accept/reject feedback), and a *drift velocity* = (added + removed) / (count v1 + count v2) **[src for the formula]**. Output in JSON or KGCL. | Not stetiq's **Drift** (Observed Schema vs Contract Alias). OO's "drift" is a version-to-version diff, i.e. stetiq's **Ontology Diff**. The rename suggestion has no stetiq counterpart. | none | #201 (named "drift" there); rename suggestions belong with #199 |
| `onto_version` / `onto_history` / `onto_rollback` | Named snapshots of the *whole store* in SQLite; rollback restores one into the store. | **Ontology Version** (immutable, numbered) and **Alias**. stetiq's "rollback" is moving the Contract Alias back, which is a Promotion. | Restoring the graph: **0001** | #201 |
| Lineage (`onto_lineage`, REST `/api/lineage`) | Append-only SQLite log of one line per lifecycle call: session, seq, timestamp, event letter, operation, a short detail string (for plan: `"computed"`; for apply: the mode) **[src]**. No actor beyond the session id; no plan content. Optional `GOVERNANCE_WEBHOOK` POSTs every event to an external enforcer (OpenCheir). | The **Promotion** audit (actor from the **API Token**, whether the latest **Gate** result passed), recorded Gate and **Consumer Gate** results, Construction Run provenance. stetiq's audit already says more per event. | none | #201 |
| Enforce + lint feedback | Design-pattern packs (`generic`, `boro`, `value_partition`, custom SPARQL). Dismiss a warning 3 times and it is suppressed; accept once and it sticks. | Built-in **Evaluators** and **Gates**. stetiq has no learned suppression. | none | the rest (#202) |

### 3. The MCP server and its `onto_*` tools

(README › *Connect the tool to Claude*; `docs/tool-reference.md`; `CLAUDE.md` › *Architecture Convention: MCP-Native Tool Design*; `src/main.rs` `serve-http` **[src]**)

- **Transports.** `serve` (stdio), `serve-http` (streamable HTTP at `/mcp`, plus a REST API at `/api/{stats,query,update,load,load-turtle,save,batch,lineage}` and an open `/health`), `serve-unix`, and a `daemon` that keeps an in-memory store alive between CLI calls.
- **124 tools**, one line each in `docs/tool-reference.md`. That page is generated from the `#[tool]` attributes and a test fails the build if a tool has no line.
- **Tool profiles.** `full` (default), `authoring`, `validation`, `reasoning`, `alignment`, `governance`, `data`, `planning`, `retrieval`, `evaluation`. Each profile carries the same floor (`status`, `validate`, `load`, `query`, `stats`, `clear`). A test fails if a tool belongs to no profile. An unknown profile name refuses to start. A second axis, `--tools-allow`/`--tools-deny` with groups (`read_only`, `mutating`, `governance`, `remote`, `embeddings`, `sql`), only narrows. The stated split: "a profile asks what a client is here to do, and the allow/deny groups ask what a caller may be trusted to do."
- **Auth [src].** One optional shared bearer token for the whole server (`--token`, `OPEN_ONTOLOGIES_TOKEN`, `[http] token`). An empty token disables auth. The default bind host is `127.0.0.1`. There are no users and no per-graph permissions. CORS is permissive. All sessions share one in-memory store. REST `/api/update` runs any SPARQL UPDATE, and `/api/load` reads any path on the server's disk.
- **Design convention** (`CLAUDE.md`): the server never embeds its own LLM. It returns what needs judging (borderline alignment pairs, CQ results), the connected agent judges, and verdicts come back through feedback tools (`onto_align_feedback`, `onto_verify_cq`, `onto_lint_feedback`). `CLAUDE.md` also ships a 17-step workflow telling the agent what to call in what order.

**Mapped to stetiq.** stetiq has no MCP server. `docs/vision.md` › *AI and MCP authoring* plans one ("lets agents read and edit a Use Case… AI only ever proposes. A person accepts what becomes a new Use Case Version") and leaves it "for a later team". The nearest shipped things are the SDK `Client`, the REST API under `/api/v1` with per-Knowledge-Graph *read*/*edit* **API Tokens** (ADR 0002), and the LLM question mapper (`--question-mapper`), which is an embedded LLM: the opposite of OO's "no LLM in the server" convention.

| OO part | Nearest stetiq concept | ADR? | Ticket |
|---|---|---|---|
| MCP transport over the tracking API | REST `/api/v1` + SDK; vision's planned MCP server | none, if it wraps the tracking service. An MCP tool that queries the Graph Source from the server side would need **0005**. | agent access (#200) |
| Tool profiles / allow-deny groups | API Token *read*/*edit* per Knowledge Graph (the "may be trusted" axis). Nothing matches the "what is the client here for" axis. | none | #200 |
| Shared bearer token, permissive CORS | stetiq is already stricter (per-user tokens, fail-closed routes, CSRF). Pitch contrast, not adoption. | none | #200 |
| "Server returns what needs judging; agent judges; feedback tool records it" | Vision's "AI only ever proposes; a person accepts" (as in **Adoption**). The question mapper goes the other way today. | none | #200 |
| Agent workflow in `CLAUDE.md` | No counterpart. | none | #200 |

### 4. Certificates and evidence

| Capability | What it does | Nearest stetiq concept | ADR? | Ticket |
|---|---|---|---|---|
| Derivation certificate (`reason --certificate`) + Lean checker `oo-cert` | Each inferred triple written as rule + conclusion + premises in two TSV files; `OOCert.certificate_sound` proves that an accepted certificate contains only entailed triples. A forged line is refused, naming the rule. `asserted.sha256` binds it to the input bytes. | None. stetiq derives nothing (ADR 0006). The nearest *evidence* idea: a recorded **Gate** result is "what Promotion's audit trusts" (ADR 0007), and stetiq never records a Gate Preview because "a result computed from Gates the server merely remembers… would claim more than it knows". | **0006** | audit and evidence (#201), pitch contrast |
| Verdict words that cannot over-claim (`entailed` vs `entailed_under_supplied_rules`, `checker_absent_nothing_was_checked`, measured vs proved vs opinion) | Mirrors stetiq's rule that a missing baseline or input is never a pass (Consumer Gate) and ADR 0007's "a preview is labelled, never recorded". | none | #201 / practices (#203) |
| `onto_pack` / `onto_unpack` (decision 0017) | Graph + lint/enforce evidence + optional certificate as sorted N-Triples with a manifest and a `content_sha256`. The receiver *re-runs its own checker*; a refused certificate blocks the load. Meant for "promoting a graph between environments". | **Promotion** + content hash (stetiq dedupes versions by sha256 of canonical JSON). The decision's core rule, "the receiver re-derives, it does not trust the sender's report", echoes stetiq's "the server is the authority for verdicts" (`tests/test_server_trust.py`). | The pack carries instance data: **0001** | #201 |
| Justification, provenance semirings, repair (`onto_justify`, `onto_provenance`, `onto_repair`) | Which asserted axioms a conclusion or contradiction rests on; the cheapest axiom set to drop to make every class coherent. | None. | **0006** | the rest (#202) |

## The rest of the catalogue, grouped

All belong to the "the rest" verdict ticket (#202) unless noted. Tool names are from `docs/tool-reference.md`.

| Group (tools) | What it does | Nearest stetiq concept | ADR? |
|---|---|---|---|
| Reasoning (`onto_reason`, `_incremental`, `onto_classify_el`, `onto_dl_check`, `onto_dl_explain`, `onto_dlp_boundary`, `onto_trace_label`, `onto_rules_import`, `onto_compile_exceptions`) | RDFS/OWL-RL/OWL-RL-ext materialisation, SHIQ tableaux, EL classification, SWRL/RIF import into Horn tables, which axioms the rule table can "see". | None. | **0006** |
| First-order export and provers (`onto_fol_export`, `onto_fol_model`, `onto_fol_prove`, `onto_convert` to OFN) | TPTP/CLIF/SMT-LIB/LADR export; model finding and prover output re-checked where possible. | None. | **0006** |
| `onto_defects` | Eight TBox self-defect kinds (subclass cycle, disjoint with ancestor, transitive+functional, …). | Version built-in Evaluators (`hierarchy`, `constraint_consistency`). Closest adoptable idea in this group. | none for cycle-style checks; disjointness is not yet a stetiq Axiom kind (ADR 0006 › Consequences) |
| `onto_lint`, `onto_enforce` (+ feedback) | Missing labels/comments/domains/ranges; pattern packs. | `definitions`, `orphan_concepts` Evaluators. | none |
| SHACL (`onto_shacl`, `onto_shacl_check`, `onto_shape_induce`, `onto_shape_combinatorics`, `onto_owl_shacl_coevolve_*`) | SHACL validation with a Lean-verified evaluator; data-driven shape induction. Decision 0018: "conformance is not truth", and a report must say which shapes selected nothing. | **Conformance** (closed-world, on the Observed Schema). ADR 0006 deliberately avoids a second set of validation rules. | Validating instance data in the core: **0001**, **0005** |
| `onto_vocab_check` | Closed-world check that every predicate and class used in a data graph is declared ("catches hallucinated terms"). | **Conformance** and **Drift** (undeclared Concepts in the Observed Schema). stetiq already does this closed-world, on aggregates. | Running it on a data graph in the core: **0001** |
| Competency questions (`onto_cq_run`, `onto_verify_cq`, `onto_cq_verdicts_list`) | Run a batch of SPARQL CQs against the loaded store, pass/fail with pitfall hints; store an LLM- or human-supplied verdict per CQ. | **Competency Question** and executed CQ results (SDK-side through `execute_read`, ADR 0005). stetiq ties CQs to **Tasks** and **Consumers**; OO's CQs float free of any consumer. | Running in the core against the graph: **0005** |
| Evaluation (`eval_rag`, `eval_rag_mmrag`, `onto_eval_alignment`, `borderline_*`) | mmRAG and OAEI P/R/F1 scoring. | **Evaluator** (stetiq's pluggable measurement). | none |
| Data pipeline (`onto_ingest`, `onto_sql_ingest`, `onto_sql_sync_*`, `onto_map`, `onto_extend`, `onto_import_schema`, `onto_induce`, `onto_pull`, `onto_push`) | Load CSV/JSON/XML/YAML/XLSX/Parquet/Postgres/DuckDB into RDF; CDC watermarks; relational schema → OWL; one sheet → class + shape + mapping. | **Construction Run** behind the **Construction Entry Point** (a black box to stetiq). `onto_induce`'s "induce structure from data" resembles **Adoption** from an **Observation**. | **0001**, **0005** |
| Retrieval for RAG (`onto_segment_retrieve`, `onto_module_extract`, `onto_closure_diff`, `graph_projection_*`, `onto_communities`, `onto_extract_scaffold`, `onto_extract_validate`) | Locality modules with a cited theorem; slice-preserves-entailment checks; schema-guided extraction scaffolds for LLMs. | None. `onto_extract_scaffold` is near a Declared Ontology handed to an extraction pipeline. | Modules/slices: **0006**; extraction scaffolding: none |
| Alignment (`onto_align*`, `crosswalk-certify`, `crosswalk-probe`) and clinical crosswalks | Weighted multi-signal matching with learned weights; SSSOM output; downgrades unsupported `exactMatch`. | Gold-ontology alignment, which consolidation spec #146 **cuts**. | none, but already cut |
| Embeddings (`onto_embed`, `onto_search`, `onto_similarity`, `onto_hnsw_build`) | Text + Poincaré embeddings, semantic search. | None. | none |
| Dynamics and planning (`onto_action_*`, `onto_invariant_*`, `onto_default_*`, `onto_plan_compile_pddl`, `onto_plan_classical`, `onto_plan_validate`, `onto_certify_action` (CIVeX), `onto_policy_*` (ARGOS)) | Registered state-changing actions with SPARQL preconditions, BC+ invariants, PDDL compilation, causal certificates, allow/deny SPARQL ASK policies. Not related to `onto_plan`. | None. | **0001** (acts on instances) |
| Temporal and provenance (`onto_temporal_*`, `onto_support_*`) | Valid-time/record-time snapshots; whether cited sources support a claim. | None. | **0001** |
| Packaging and distribution (`onto_marketplace` with 33 standard ontologies, `onto_plugin_*` WASM plugins, `onto_cache_*`, `onto_repo_*`, `onto_ossie_import`) | Catalogue install, plugins, compile cache. | None. | none |
| Studio (Tauri desktop app) | Virtualised ontology tree, AI chat panel driving the MCP tools, Protégé-style inspector, lineage panel. | stetiq web UI (Ontology Map/Table, frozen in the MVP). | none |
| Hosted platform (tesseractsemantics.com) | "The place for the evidence": keeps certificates, reviews each change, lets an auditor re-check. | stetiq server + audit. Direct commercial overlap. | n/a (pitch) |

## Engineering practices

All go to the practices ticket (#203). No ADR applies to any of them.

| Practice | What it is (source) | stetiq today |
|---|---|---|
| Tests recompute README numbers | `readme_example_test.rs`, `demo_asset_claims_test.rs`, `certified_claims_asset_test.rs`: each figure's count is recomputed and the test fails if caption and run disagree. "Nobody writes a count into the caption." (README, `docs/ci-gates.md`) | No equivalent check on README or guide numbers. |
| Measured / proved / opinion wording | Anything checked by a Lean theorem is *proved*; a test-computed property is *measured*; a second solver is an *opinion* that "can contradict and cannot confirm" (decision 0013). Verdict words are minted only by one function (`verdict.rs`, decision 0017). | ADR 0007's "labelled, never recorded" Gate Preview and "a missing input is never a pass" share the spirit. |
| Writing rules enforced by a test | README follows ASD-STE100 rules (≤ 25 words per sentence, ≤ 6 sentences per paragraph, one term one meaning); `readme_simplified_english_test.rs` fails the build on a breach and holds the Chinese README to the same structure. | `GLOSSARY.md` "Avoid" lists and CLAUDE.md wording rules, not tested. |
| A decision record per rule | `docs/decisions/`: one file per rule, each naming "the failure it prevents" and what it has caught. `decision_numbers_test.rs` fails on duplicate numbers, missing index rows or dangling links (four numbering collisions from parallel branches caused it). Holes are kept, never reused. | `docs/adr/` (8 ADRs), no index test. |
| A skip is not a pass | `skip_unless` + `OO_REQUIRE_FIXTURES=1` turns a missing toolchain into a failure in any job that should provide it; `ci_gate_coverage_test.rs` reconciles `docs/ci-gates.md` against `tests/` and workflows. Motivated by a differential suite that "skipped every test… and exited 0". No mechanism; a missing Postgres or browser toolchain is avoided by convention. |
| Generated, test-gated tool reference | `docs/tool-reference.md` generated from `#[tool]` attributes; `tool_reference_test.rs` fails on an unlisted tool; profile sizes are measured, never typed. | stetiq's guide (ADR 0004) is hand-written, with no coverage test. |
| Independent checkers and differentials | Lean, Isabelle and Rocq kernels written from the spec; Rust vs Python engines; SHACL vs pyshacl. The README states the two engines are *not* independent. | n/a (stetiq has no reasoner to check). |
| "A missing block and a clean block look the same to a dashboard" | Every optional check emits its block with `ran: false` and a reason instead of disappearing (`plan`'s `conservativity`, `logic`). | Same instinct in Consumer Gate's "missing baseline fails". |

## Docs and code that disagree

Findings for whoever writes pitch contrast. Each is small, but each is a place where OO's own standard ("a claim must not say more than was checked") slips.

1. `onto_lock` says "prevent removal during plan/apply". The code only reports the violation; neither the risk score nor `apply` reads it **[src]**.
2. `onto_apply`'s tool text says `safe` is "clear+reload". `docs/lifecycle.md` and the code write a triple delta and reload only when blank nodes are present **[src]**.
3. `docs/lifecycle.md` › *Monitor* describes "SPARQL watchers". A watcher with any other `check_type`, or with no query, is accepted and then silently scores 0 and passes **[src]**: the "a skip is not a pass" rule the project applies to its tests does not reach its monitor.

## Summary for the verdict tickets

- **Change planning (#199).** OO's blast radius is "triples in the store that mention a removed IRI" and its risk score is three hard-coded levels driven by removals plus a logic check. Neither knows about downstream users. stetiq's **Consumer impact** already answers the question OO's blast radius only gestures at, which makes it the main pitch contrast: *OO tells you how many triples a change touches; stetiq tells you which Consumer's Task it breaks.* Candidate ideas that pass the ADR lenses: a single summary risk level on the Ontology Diff, weighting a removal by **Observed Schema** counts (aggregates only), locked Concepts as a Gate shorthand, rename *suggestions* in the diff. Conservativity and the ABox half of the logic block need ADR 0006 or 0001 reopened.
- **Agent access (#200).** OO's MCP server is broad (124 tools), profile-scoped and well documented, but auth is one shared optional token over one shared store. Its "no LLM in the server; the agent judges, a feedback tool records it" convention matches stetiq's vision ("AI only ever proposes"). An MCP server over the tracking service needs no ADR. Anything that reaches the graph does (0005).
- **Audit and evidence (#201).** Certificates need a reasoner (0006). Apply, monitor actions and rollback write the graph (0001, 0005). Lineage is thinner than stetiq's Promotion audit. The transferable idea is the evidence discipline (decision 0017: the receiver re-derives, never trusts the sender's report), which stetiq already practises server-side.
- **The rest (#202).** Almost everything is reasoning, instance-data handling or RAG tooling. All are outside stetiq's scope by ADR 0001/0005/0006, or already cut (alignment). `onto_defects` is the one TBox-only check worth comparing with stetiq's built-in Evaluators.
- **Practices (#203).** Every listed practice is real and test-enforced in OO, and none collides with an ADR.
