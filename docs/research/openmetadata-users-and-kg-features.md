# Who uses OpenMetadata, and does it have its own knowledge-graph features?

Research for [#191](https://github.com/JoaZaech/stetiq/issues/191), part of the wayfinder map [#186](https://github.com/JoaZaech/stetiq/issues/186). It builds on the market landscape in [#136](https://github.com/JoaZaech/stetiq/issues/136), which did not cover OpenMetadata. Sources were checked on 2026-11-02.

## Answer

- **Users.** OpenMetadata is used by data-platform and governance teams that run warehouses and lakehouses. None of the published adopters or case studies mentions a graph database, an ontology or LLM extraction into a Knowledge Graph.
- **Knowledge-graph features.** OpenMetadata now has substantial ones, but all of them point at *its own catalog*:
  - an RDF/SPARQL projection of the catalog's metadata (beta, off by default);
  - SKOS-style glossary relations and OWL import;
  - a governed "Ontology Studio" (in development on `main` and the 2.1 line), where ontology releases are approved, diffed against a baseline, activated and rolled back;
  - a Neo4j connector that catalogs a graph's *schema* (from 2.1).

  None of these judges the instance output of an LLM→KG pipeline against a Declared Ontology or against what its Consumers need.
- **Verdict: a neighbour, moving closer.** It is not a direct competitor today, and it is not irrelevant. The overlap is the *language* of governed ontology releases, review and diff, and the "context layer for AI agents" pitch. The function differs: OpenMetadata governs a business ontology over catalog metadata, while stetiq gates the output of an extraction pipeline.
- **"Integrate with OpenMetadata" is not a live ruling** for stetiq's target users. #186 makes *integrate* conditional on evidence that LLM→KG engineers run OpenMetadata, and there is none. The only plausible future edge is a Connector that publishes stetiq's Gate verdicts or Ontology Versions into a customer's existing OpenMetadata. That would fit ADR 0005 (connectors at the edge), but it is "validate in pilot interviews" at most.

## 1. Who runs OpenMetadata

| Evidence | What it shows | Source |
|---|---|---|
| Repo: about 15.7k stars, 2.5k forks, Apache-2.0, pushed daily | Large, active open-source project | GitHub API, `repos/open-metadata/OpenMetadata` (2026-11-02) |
| Site claims: "4,000+ Enterprise Deployments", "14,000+ Open Source Members", "500+ Code Contributors", "130+ Data Connectors" | Mainstream data-catalog adoption | [open-metadata.org](https://open-metadata.org/) |
| Site logos: Wix, FreeNow, OpenAI, Gorgias, inDrive, Carrefour, Yelp, PayU Finance, Forter, Loggi, VRT and others | Consumer-internet, retail and fintech data teams | [open-metadata.org](https://open-metadata.org/) |
| Collate customer stories: Yelp (replaced a legacy catalog, 100K+ entities), Gorgias (cleaning up unused warehouse models), Woop (dbt + Metabase lineage), Loggi and VRT (data quality), Forter (S3 metadata), Ambry Genetics (PHI scope over 6 MySQL databases), UnionBank (compliance), OpenAI (an internal data agent over the catalog), Unity (a Slack Q&A bot), FDNY (data model connected to Claude) | The use cases are catalog, lineage, data quality and governance over SQL/warehouse/lake sources. The AI uses are agents that *read* the catalog | [getcollate.io/customers](https://www.getcollate.io/customers) |
| Customer page, searched for graph DBs, ontologies, KG, LLM extraction | None mentioned | same |

The connectors tell the same story. The ingestion tree (`ingestion/src/metadata/ingestion/source/`) contains about 70 database connectors (Snowflake, BigQuery, Databricks, Postgres, …), plus dashboard, pipeline (Airflow, dbt, Dagster, Fivetran, OpenLineage), messaging, ML-model (MLflow, SageMaker), storage, search and drive connectors, and a `source/mcp` service type. Its only graph-database connector is Neo4j (§3). It has none for Neptune, Stardog, GraphDB, TigerGraph, Memgraph or other RDF stores ([repo tree](https://github.com/open-metadata/OpenMetadata/tree/main/ingestion/src/metadata/ingestion/source)).

**Inference.** The buyer is a data-platform or governance lead at an organisation with a warehouse. stetiq's user is an AI/software engineer who owns an LLM extraction pipeline. They can belong to the same company, but they are different people with different budgets. No primary source shows OpenMetadata used *by* LLM→KG pipeline teams.

## 2. OpenMetadata's own knowledge-graph features

### 2.1 RDF Knowledge Graph (shipped, beta, off by default)

- It "represents your metadata as RDF triples in a Fuseki triplestore". It is "an optional feature, disabled by default" and is labelled Beta ([docs v2.0.x](https://docs.open-metadata.org/v2.0.x/deployment/rdf-knowledge-graph)). The docs have a page for it since the v1.12.x line.
- It provides a SPARQL query and update API (`/api/v1/rdf/sparql`), a JSON-LD representation of every entity, and semantic search over the graph (which needs OpenSearch) (same page).
- 1.13.0 (8 June 2026) made it a headline: "Requires Apache Jena … Run the RDF Knowledge Graph Index App". The same release added a governance page at `/governance/ontology` and glossary "concept mappings for external IRIs and SKOS-style relation types" ([release notes](https://docs.open-metadata.org/v1.13.x/releases/all-releases)).
- The graph's own ontology, `openmetadata-spec/.../rdf/ontology/openmetadata.ttl`, imports DCAT, PROV and SKOS. It also uses DQV, DPROD, ODRL, CSVW and others. 18 SHACL NodeShapes (`rdf/shapes/openmetadata-shapes.ttl`) validate *OpenMetadata's own metadata triples*. Ontology "packs" ship for FIBO, FHIR, GS1, ISA-95, EPCIS and HR-Open ([repo](https://github.com/open-metadata/OpenMetadata/tree/main/openmetadata-spec/src/main/resources/rdf)).
- The scope is the catalog only. The ADR "The RDF graph projects the live catalog only" (2026-10-26) defines the graph as the live catalog's entities and lineage edges ([docs/decisions](https://github.com/open-metadata/OpenMetadata/blob/main/docs/decisions/2026-10-26-the-rdf-graph-projects-the-live-catalog-only.md)).

### 2.2 OpenMetadata 2.0 (24 Aug 2026): "open context layer for AI agents"

- 2.0.0 shipped OWL Import ("Import OWL … files to load existing ontologies and classification taxonomies"), Context Center, and an MCP server that is on by default ("Starts ready on upgrade") ([2.0 release notes](https://docs.open-metadata.org/v2.0.x/releases/2.0-release.md)). In 2.0.3 the Fuseki extension became optional, and 2.0.6 made ODCS data-contract rules create linked test cases (same).
- The README pitches "Metadata, Meaning, Memory": governed memory entities for agents, semantic search, and MCP tools ([README](https://github.com/open-metadata/OpenMetadata/blob/main/README.md)). The MCP server has been a first-class service category since 1.13.0 and is published to the MCP Registry since 1.13.1 ([release notes](https://docs.open-metadata.org/v1.13.x/releases/all-releases)).

### 2.3 Ontology Studio: governed ontology releases (on `main`, 2.1 line, unreleased)

The design doc ["Governed organizational ontologies in Ontology Studio"](https://github.com/open-metadata/OpenMetadata/blob/main/docs/plans/2026-10-14-organizational-ontology-design.md) is present on the `2.1.0-rc1-release` tag (28 Oct 2026). It says outright: "Ontology Studio is unreleased." It contains:

- Native OWL/SKOS concepts, properties and axioms stored in SQL. An immutable **release** is the only approval unit, with semantic versions ([ADR 2026-10-19](https://github.com/open-metadata/OpenMetadata/blob/main/docs/decisions/2026-10-19-ontology-releases-allocate-semantic-versions.md)).
- Review that shows "a comparison against the captured baseline, including before/after payloads and removals", followed by activation, rollback, and projection of the active release into Fuseki.
- Validation of "Structure and supported OWL 2 DL profile". "Logical consistency is `NOT_RUN`" until Jena reasoning is added.
- "Memory proposals" (typed change sets from agent memories) that still have to pass release review. AI-proposal review and live-data execution are **Collate (commercial) extensions** ([ADR 2026-10-16](https://github.com/open-metadata/OpenMetadata/blob/main/docs/decisions/2026-10-16-ontology-ai-proposal-review-is-a-collate-extension.md), [ADR 2026-10-21](https://github.com/open-metadata/OpenMetadata/blob/main/docs/decisions/2026-10-21-ontology-live-data-execution-is-a-collate-extension.md)).
- Concepts bind to *catalog columns*. "Live data" means OpenMetadata generates a `SELECT … LIMIT 50` over SQL warehouse dialects (ANSI, Snowflake, BigQuery, MySQL, Spark, T-SQL) for Collate to run. Records "stay in the source and nothing is stored" (ADR 2026-10-21).
- The plan lists as follow-ups: metadata-to-concept annotations, Jena consistency checks, and "source mappings".

**What it is not.** Nothing in these sources checks instance data from an extraction run against the ontology. Nothing tracks an observed schema or conformance across runs, and nothing ties an ontology change to named downstream consumers or their competency questions. The ontology is a *business semantic layer over the warehouse*, not the target schema of an LLM→KG pipeline.

## 3. Graph databases as sources: the Neo4j connector

- It was added on 2026-10-16 in "Fixes #34249: Add Neo4j database connector (#34250)". It is on the `2.1.0-rc1-release` tag but not on `2.0.7-release`, so it first ships with 2.1 (GitHub API, commits on `ingestion/.../neo4j/metadata.py`).
- It maps the graph *schema* onto the SQL hierarchy: database → the Neo4j database; schemas → `nodes` and `relationships`; tables → node labels and relationship types; columns → their properties, typed from `db.schema.*TypeProperties()`. "No node or relationship data is read beyond what the schema procedures return" ([connector doc](https://github.com/open-metadata/OpenMetadata/blob/main/openmetadata-ui/src/main/resources/ui/public/locales/en-US/Database/Neo4j.md), [metadata.py](https://github.com/open-metadata/OpenMetadata/blob/main/ingestion/src/metadata/ingestion/source/database/neo4j/metadata.py)).
- Its service spec is `DefaultDatabaseSpec` with only metadata and connection classes, so the connector itself declares no profiler, data-quality or lineage support.

**Inference.** After 2.1, a Neo4j-backed KG can appear in an OpenMetadata catalog as "tables" (labels) with "columns" (properties). That is a crude cousin of stetiq's Observed Schema: a single snapshot, with no conformance to a Declared Ontology, no statistics and no drift. Because labels become table entities, OpenMetadata's table-level Data Contracts and tests *could* be attached to them, but no source shows anyone doing that for a KG.

## 4. Competitor, neighbour, or irrelevant?

| stetiq concept | Closest OpenMetadata feature | Overlap |
|---|---|---|
| Ontology Version, Ontology Diff, Promotion | Ontology Studio releases: baseline diff, approval workflow, activate and rollback (unreleased) | **High in vocabulary, low in purpose.** OpenMetadata versions a hand-authored business ontology, while stetiq versions the ontology that an extraction pipeline is gated against |
| Gate (Conformance + Observed Schema statistics + Drift) | SHACL shapes over OpenMetadata's *own* metadata; table data-quality tests on SQL sources | Low. Nothing runs over KG instance output |
| Consumer Gate, Consumer impact | Data Contracts (ODCS) on tables and data products; lineage-based impact | Medium, as an *idea* (consumer-facing contracts). Different object: warehouse tables, not ontology-scoped Competency Questions |
| Graph Source | Neo4j connector (schema only, from 2.1) | Low to medium. Same input surface, no evaluation |
| Planned MCP schema-server Connector | OpenMetadata MCP server (on by default) | Medium. Both expose schema/context to agents |

**Verdict: neighbour.** OpenMetadata is a catalog and governance platform for warehouse teams that is quickly adding semantic-web machinery (RDF, SPARQL, SHACL, OWL, SKOS, governed ontology releases) to become an "AI context layer". It does not evaluate LLM-built graphs. Of #136's categories it fits "ontology governor" (like TopBraid EDG), with a catalog attached.

## 5. Implications for #186 and the pitch

1. **Integrate stays off the table** as a default ruling. No evidence shows LLM→KG engineers running OpenMetadata. Every *integrate* candidate in #186 should be judged *adopt the concept* or *skip* unless pilot interviews turn up OpenMetadata in a target user's stack.
2. **Positioning note for the consolidation map (#135).** Once Ontology Studio ships, "versioned, reviewed, diffed ontology releases" will no longer set stetiq apart, because a free, Apache-2.0 platform with 4,000+ deployments will offer it. This confirms #136's conclusion: lead with "governance for LLM-built graphs, judged by their Consumers" (Gate on instance-free Observed Schema statistics plus Consumer Gate), not with ontology versioning.
3. **Concepts worth studying for adoption** (for sibling tickets, not decided here): releases as the only approval unit, with a captured baseline and the diff in the review; ODCS-style contracts as the external shape of a Consumer Gate; and OpenMetadata's MCP server design as a reference for the planned MCP Connector.
4. **Optional future edge**, not for the MVP: an outbound Connector that writes stetiq Gate results to OpenMetadata (for example as test results on the Neo4j-label "tables"). This could suit enterprise pilots whose data teams already run OpenMetadata. Validate in pilot interviews.

## Open questions

- Whether any LLM→KG team actually runs OpenMetadata or Collate. Only pilot interviews can answer this, since public case studies do not.
- When Ontology Studio is released (2.1 GA?), and whether "source mappings" grow into checking instance data against the ontology. That would move OpenMetadata from neighbour toward competitor. Re-check the `docs/plans` and `docs/decisions` folders of the OpenMetadata repo after 2.1 GA.
