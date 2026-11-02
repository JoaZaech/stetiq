# How OpenMetadata Data Contracts work

Research for [#187](https://github.com/JoaZaech/stetiq/issues/187), under the wayfinder map [#186](https://github.com/JoaZaech/stetiq/issues/186). Sources read 2026-11-02, against OpenMetadata `main` and the 2.0.x docs (latest release 2.0.7, 2.1.0-rc1 in pre-release). OpenMetadata terms (Data Contract, Incident, Lineage, Test Suite) are OpenMetadata's. stetiq terms are as defined in `GLOSSARY.md`.

## Answer in brief

An OpenMetadata Data Contract is a **producer-side, post-hoc check that one catalog asset (typically a Table) still matches what was promised**. It is checked daily, or on demand, against the asset's current catalog metadata and its data-quality test results. It records a pass or fail result. It does not block anything. It has no notion of a consumer beyond documentation fields and owner notifications that follow lineage. It has no notion of a *change* between two contract versions being safe or breaking for someone.

That puts it next to stetiq's **Contract Alias + Drift** (does the live store still match the declared structure?), not next to the **Gate** or **Consumer Gate** (may this change ship, and what would each Consumer lose?). The Consumer Gate has no OpenMetadata counterpart.

## 1. What a Data Contract declares

Entity schema: [`openmetadata-spec/.../entity/data/dataContract.json`][schema]. Section behaviour: [Data Contract spec docs][spec].

| Section | Shape | Checked by a contract run? |
|---|---|---|
| `schema` | Array of OpenMetadata `column` objects (name, dataType, constraints…) | Yes. Each declared field must exist on the asset. Duplicates fail. Type mismatches are recorded "for informational purposes but don't count as failures" ([repository code][repo], `validateSchemaFieldsAgainstEntity`) |
| `semantics` | Array of `semanticsRule`: name, description, a JSON Logic `rule` over the entity's metadata, `enabled`, `entityType`, `ignoredEntities`, `inherited` ([`type/basic.json`][basic]) | Yes. Evaluated by OpenMetadata's `RuleEngine` against the asset's **metadata** (e.g. "has an owner", "has a description"), not its data. The docs say these rules "don't block edits to the asset" ([spec]) |
| `qualityExpectations` | References to OpenMetadata Test Cases, collected in the contract's `testSuite` | Yes, tables only. Runs the test-suite pipeline asynchronously, i.e. **queries instance data** ([validate API][validate]) |
| `sla` | `refreshFrequency`, `maxLatency`, `availabilityTime`, `timezone`, `retention`, `columnName` | **No.** "A contract run doesn't check SLA values." `slaValidation` exists in the result schema but is not populated ([spec]) |
| `security` | `dataClassification`, `policies[]` (access policy, `identities` = "Consumer AD Groups", `rowFilters`) | **No.** "OpenMetadata doesn't enforce the security section or check it against its own policies" ([spec]) |
| `termsOfUse` | Markdown "for both human and AI agents consumption" | No |
| Metadata | owners, reviewers, `entityStatus`, `effectiveFrom`/`effectiveUntil`, `sourceUrl`, `contractUpdates[]` | No (informational) |

`odcsQualityRules` and `odcsElementExtensions` store ODCS content that has no OpenMetadata equivalent, so it survives a round trip ([schema]).

## 2. What it attaches to

- `entity` is a single required `entityReference` ([schema]). **Each asset has at most one contract** ([spec]).
- Full support (schema, plus quality for tables) covers Table, Topic, API Endpoint and Dashboard Data Model. About fifteen more asset types (Database Schema, Pipeline, ML Model, Data Product…) accept only the metadata sections. Unsupported sections are rejected with a 400 ([spec]).
- **Inheritance.** An asset inherits the contract of its Data Product. Since 2026-10-19, a table also inherits the contract of its database schema. A parent contract passes down only when it is **Approved**. The asset's own contract is merged over it ("own fields win, rules are unioned"). An asset that has only an inherited contract gets it as a `Draft` copy, so the inherited rules are not enforced on it ([OpenMetadata decision record][inherit]).

## 3. Who validates, and when

- **On demand.** "Run now" on the asset's Contract tab, `POST /v1/dataContracts/{id}/validate`, or `POST /v1/dataContracts/entity/validate`. Each needs the Edit All permission ([validate]).
- **Scheduled.** The *Data Contract Validation* application "validates every contract on a schedule, daily at midnight by default" ([validate]; app definition `DataContractValidationApplication.json` in the service resources).
- **Not on change.** No check runs when the asset or contract is edited, and nothing gates a producer's change before it lands ([spec]).
- **Mechanics.** Schema and semantics are checked synchronously, inside the OpenMetadata server, against the catalog's own copy of the asset's metadata (`Entity.getEntity(...)` in [repository code][repo]). Quality starts the test-suite pipeline, returns `Running`, and is completed when the tests report. A new run aborts one still in progress ([validate]).
- **Statuses.** `Running`, `Success`, `Failed` and `Aborted`. `PartialSuccess` and `Queued` are reserved, for results pushed by external tools ([validate]; [`contractExecutionStatus.json`][status]).

## 4. What happens on a violation

- A `DataContractResult` time-series row is stored, with per-dimension `schemaValidation` (failed field names), `semanticsValidation` (failed rule names), `qualityValidation` and an optional `incidentId` ([`dataContractResult.json`][result]). The contract's `latestResult` is updated.
- The UI shows an execution-history chart. When the latest run failed, the asset header shows a button that opens the contract ([spec]).
- A `ChangeEvent` is written for each result ([repository code][repo]). Alerts can route it to **owners of the asset and of every asset downstream of it in lineage**: `DataContractLineageResolver` maps the contract to its asset "so downstream notifications can properly traverse lineage", and `LineageBasedDownstreamHandler` resolves the recipients of "every entity downstream" ([resolver]).
- **Incidents.** OpenMetadata 1.8 announced contracts as "natively integrated with OpenMetadata's Test Suite and Incident Manager" ([1.8 release blog][rel18]). In the code, the incident link goes through the Test Cases: a failing quality test raises an Incident Manager incident as any test would. The current repository never sets the result's own `incidentId`; a code search for `withIncidentId` hits only `TestCaseResultMapper`.
- **Nothing is blocked.** No ingestion, pipeline or merge is stopped. A contract is a status report.

## 5. Versioning

- A contract is an ordinary OpenMetadata entity. It carries the generic entity `version` and `changeDescription` from `entityHistory.json`, plus a `contractUpdates[]` log of `{timestamp, updatedBy, version, changeDescription}` ([schema]).
- Lifecycle uses the generic `entityStatus`: Draft, In Review, Approved, Rejected, Deprecated, Archived. An older `contractStatus` enum (Draft/Active/Deprecated) is still defined in the schema. "OpenMetadata has no built-in approval workflow for data contracts". If reviewers are set, only a reviewer can approve or reject. UI-created contracts are saved as Approved ([spec]).
- An ODCS `version` field is **not** imported: "OpenMetadata versions the contract itself" ([ODCS docs][odcs]). There is no semantic version, no immutable snapshot that a consumer pins, no diff between contract versions, and no breaking/additive classification. `effectiveFrom`/`effectiveUntil` are informational only.
- **ODCS.** OpenMetadata imports and exports ODCS `v3.1.0` YAML, and also reads v3.2.0, v3.0.x and v2.2.x. Endpoints: `POST /v1/dataContracts/odcs/validate/yaml`, `PUT /v1/dataContracts/odcs/yaml?mode=merge|replace`, `GET /v1/dataContracts/{id}/odcs/yaml`. The original file is not stored; the docs advise keeping it in version control ([odcs]). The docs give no other contracts-as-code or CI guidance.

## 6. How consumers are tied to it

They are not, structurally. The only consumer-shaped fields are `security.policies[].identities` ("Consumer AD Groups") and `rowFilters`, and these are documented, not enforced. `termsOfUse` is free text. The practical tie is **lineage**: owners and followers of downstream assets can be notified when a result changes ([resolver]). A consumer cannot declare what it relies on, pin a contract version, or set its own pass rule.

History: contracts were introduced in 1.8 (issue [#21078] set the design: "a JSON Schema-based DataContract entity that any table, topic, dashboard, or Data Product can reference"). 1.9 made them available "in the UI and via YAML for Tables" ([1.9 release blog][rel19]). 2.0.x added ODCS import reports and broader asset support ([odcs], [spec]).

## 7. Point-by-point comparison with stetiq

| Question | OpenMetadata Data Contract | stetiq Contract Alias | stetiq Gate | stetiq Consumer Gate |
|---|---|---|---|---|
| What is the contract? | A per-asset document of schema, metadata rules, test refs, SLA and security | A pointer (`production`) to one immutable Ontology Version, the whole KG's structure plus closed-world Axioms (ADR 0006) | A rule over Evaluator results, Conformance and the Ontology Diff | A rule for one Consumer over Observed Schema stats, Conformance, Ontology Diff and Competency Question results |
| Unit | One asset (table, topic…), at most one contract each, inherited from schema or Data Product | One Knowledge Graph's Ontology | One Construction Run or Ontology Version | One Consumer × one candidate version |
| Who owns it | Asset owner / producer, plus reviewers | Whoever promotes | Upstream pipeline's repo (`stetiq.yaml`) | The Consumer's team, declared in the Use Case (ADR 0008) |
| Checked against | The catalog's current metadata of the asset, plus test results on **instance data** | Graph Source's Observed Schema (aggregate only, ADR 0001), via Drift | Artifacts in CI (ADR 0005) | The Contract Alias baseline vs. the candidate, per Consumer |
| When | Daily schedule, or on demand | At each `stetiq observe` run (user's scheduler) | Before merge / Promotion | Before merge, or before a Consumer takes a version |
| Effect of failure | Result row, UI badge, ChangeEvent, notification of downstream owners. Never blocks | Drift alert (or Pending Migration during grace) | Fails CI; blocks Promotion | Fails that Consumer's check; never moves an Alias |
| Versioning | Mutable entity with an auto-incremented metadata version and update log; no diff semantics | Immutable Ontology Versions; Ontology Diff classed additive / deprecating / breaking | Rules versioned with the repo | Versioned with the Use Case Version |
| Consumers | Not modelled; documentation fields plus lineage-based notifications | — | — | First-class: Consumers, Tasks and Competency Questions in the Use Case; Consumer impact computed from the Diff |

Closest matches:

- **OpenMetadata `schema` validation ≈ stetiq Drift**: both ask whether the deployed store still has what the contract declares. OpenMetadata checks presence of named fields only; types are informational. stetiq's Drift also covers relations, cardinalities and fill rates, and separates Pending Migrations.
- **OpenMetadata `semantics` rules** have no stetiq analogue. They govern catalog metadata hygiene (owner, description, tags), which stetiq places out of scope (#186, Out of scope).
- **OpenMetadata `qualityExpectations`** are instance-data tests, ruled out by ADR 0001. stetiq's nearest piece is aggregate Conformance on Axioms.
- **OpenMetadata `sla` / `security` / `termsOfUse`** are declarative and unenforced even in OpenMetadata.
- **Nothing in OpenMetadata resembles the Gate or the Consumer Gate**: no pre-change evaluation, no per-consumer rule, no "what would this consumer lose" over a diff.

## 8. Implications for the map (#186)

- **Pitch / positioning.** OpenMetadata Data Contracts **do not compete with the Consumer Gate**. They are producer-declared, asset-scoped, checked after the fact against catalog metadata, and they never block. If a pitch audience says "we already have data contracts in OpenMetadata", the answer is that those contracts say what a table promises today, while the Consumer Gate says whether a given consumer can take tomorrow's ontology. The two are complementary. The overlap is with Contract Alias + Drift, and only for tabular assets. OpenMetadata has no ontology or knowledge-graph asset type to attach a contract to.
- **Vocabulary.** "Data contract" is now mainstream, and ODCS v3.1 is the exchange format OpenMetadata speaks. stetiq's word "contract" (Contract Alias) means the same thing, the promised structure. This supports the positioning; it does not argue for renaming.
- **Concepts worth borrowing**, for later tickets to judge:
  - A **per-run result time series with a per-dimension breakdown** (schema / semantics / quality → for stetiq: Drift / Conformance / Competency Questions) and a status history chart.
  - **Lineage-routed notification** of downstream owners. stetiq's Consumer impact is a sharper version of this, computed from Competency Questions rather than lineage.
  - **Inheritance of a contract from a container**, approved-only, with the child's rules merged over the parent's. This is weakly relevant to Use Case defaults.
- **Integrate?** A plausible edge-only integration (ADR 0005): export the Contract Alias's Ontology Version, or a Consumer Gate verdict, as an ODCS document or an external `DataContractResult` (`PartialSuccess`/`Queued` are reserved for external producers). This only matters if pilot users run OpenMetadata. **Validate in pilot interviews.**
- **ADR limits.** Quality expectations (instance-data tests) and SLA freshness checks would breach ADR 0001 and ADR 0005 if stetiq adopted them in its core.

[schema]: https://github.com/open-metadata/OpenMetadata/blob/main/openmetadata-spec/src/main/resources/json/schema/entity/data/dataContract.json
[basic]: https://github.com/open-metadata/OpenMetadata/blob/main/openmetadata-spec/src/main/resources/json/schema/type/basic.json
[result]: https://github.com/open-metadata/OpenMetadata/blob/main/openmetadata-spec/src/main/resources/json/schema/entity/datacontract/dataContractResult.json
[status]: https://github.com/open-metadata/OpenMetadata/blob/main/openmetadata-spec/src/main/resources/json/schema/type/contractExecutionStatus.json
[repo]: https://github.com/open-metadata/OpenMetadata/blob/main/openmetadata-service/src/main/java/org/openmetadata/service/jdbi3/DataContractRepository.java
[resolver]: https://github.com/open-metadata/OpenMetadata/blob/main/openmetadata-service/src/main/java/org/openmetadata/service/alerting/audience/DataContractLineageResolver.java
[inherit]: https://github.com/open-metadata/OpenMetadata/blob/main/docs/decisions/2026-10-19-a-table-inherits-its-schemas-approved-data-contract.md
[spec]: https://docs.open-metadata.org/latest/how-to-guides/data-contracts/spec
[validate]: https://docs.open-metadata.org/v2.0.x/api-reference/data-contracts/validate.md
[odcs]: https://docs.open-metadata.org/v2.0.x/how-to-guides/data-contracts/odcs.md
[#21078]: https://github.com/open-metadata/OpenMetadata/issues/21078
Caveat: the 1.8 and 1.9 release blog posts returned HTTP 403 to a direct fetch. The quotes taken from them come from the search index, so they are the least-verified claims in this note.

[rel18]: https://blog.open-metadata.org/announcing-openmetadata-1-8-948eb14d41c7
[rel19]: https://blog.open-metadata.org/announcing-openmetadata-1-9-68b63005bb25
