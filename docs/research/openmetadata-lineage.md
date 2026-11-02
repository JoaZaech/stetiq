# How OpenMetadata builds lineage, and whether it could discover Consumers

Research for [#189](https://github.com/JoaZaech/stetiq/issues/189), part of the map [#186](https://github.com/JoaZaech/stetiq/issues/186). Read on 2026-11-02 against OpenMetadata `main` at commit [`8ec9723`](https://github.com/open-metadata/OpenMetadata/tree/8ec972354c60f5fcabca1965de7708538afc3eb6) (latest release: `2.0.7-release`, 2026-10-27). OpenMetadata terms (Lineage, Usage, Query) are OpenMetadata's. stetiq terms (Consumer, Task, Competency Question, Use Case, Graph Source) are as defined in `GLOSSARY.md`.

## Answer in brief

- **OpenMetadata lineage is write-driven.** An edge goes from the data a job reads to the data it writes. It comes from parsing view definitions and *write* statements in query logs (`INSERT … SELECT`, CTAS, `UPDATE`, `MERGE`), from dbt manifests, from pipeline and dashboard connectors, from OpenLineage events, and from manual or API edits.
- **A pure reader is not a lineage edge.** OpenMetadata records `SELECT` traffic through a separate **Usage** workflow as Query entities with the users who ran them. Its OpenLineage endpoint drops any event that lacks either inputs or outputs.
- **Granularity:** entity-to-entity edges, plus column-level lineage on table-to-table edges, from a SQL-only parser (`collate-sqllineage`, which wraps sqlglot, sqlfluff and sqlparse).
- **Graph databases:** `main` has had a **Neo4j connector** since 2026-10-16 (not yet in a release). It reads only the schema: labels and relationship types become tables, and properties become columns. It has no lineage or usage. Nothing parses Cypher or SPARQL, and OpenLineage's naming spec has no graph-store namespace.
- **For stetiq:** the *technique* carries over and the *tool* does not. "Parse the query log, attribute each query to a client, and map it to the schema elements it touches" could propose candidate Consumers, and Concept sets per Consumer, from a Neo4j query log. Three changes would be needed:
  - it uses read queries, not writes;
  - it needs a Cypher parser;
  - it runs at the edge (ADR 0005), drops parameters and masks literals before anything leaves (ADR 0001), and emits *proposals* that a person confirms into a Use Case Version (ADR 0008).

  Candidate Competency Questions come out weaker: a masked query is evidence of a question, not the question itself.

## 1. How OpenMetadata derives lineage

### 1.1 Sources of lineage

The lineage edge schema records how each edge was made in `lineageDetails.source`. Its enum is `Manual`, `ViewLineage`, `QueryLineage`, `PipelineLineage`, `DashboardLineage`, `DbtLineage`, `SparkLineage`, `OpenLineage`, `ExternalTableLineage`, `CrossDatabaseLineage` and `ChildAssets` ([`entityLineage.json`](https://github.com/open-metadata/OpenMetadata/blob/main/openmetadata-spec/src/main/resources/json/schema/type/entityLineage.json)). The docs group these as follows ([Lineage workflow](https://docs.open-metadata.org/latest/how-to-guides/data-lineage/workflow)):

| Mechanism | How | Source |
|---|---|---|
| View lineage | During metadata ingestion, view DDL is parsed for source and target tables. Postgres, for example, rebuilds `create view <schema>.<table> as <pg_get_viewdef>` | [workflow docs](https://docs.open-metadata.org/latest/how-to-guides/data-lineage/workflow); [`postgres/queries.py`](https://github.com/open-metadata/OpenMetadata/blob/main/ingestion/src/metadata/ingestion/source/database/postgres/queries.py) |
| Query-log lineage | A Lineage Agent or `metadata ingest` workflow reads the warehouse's query history and parses each statement for source and target tables. Native support covers "a limited set of connectors" (BigQuery, Snowflake, MSSQL, Redshift, ClickHouse, PostgreSQL, Databricks) | [workflow docs](https://docs.open-metadata.org/latest/how-to-guides/data-lineage/workflow); [`lineage_source.py`](https://github.com/open-metadata/OpenMetadata/blob/main/ingestion/src/metadata/ingestion/source/database/lineage_source.py) |
| Query-log file | For any other source, a CSV (or a directory of CSVs) of exported queries. Columns: `query_text` (required), `user_name`, `start_time`, `end_time`, `duration`, `cost`, plus database and schema | [`usage_source.py` L41–84](https://github.com/open-metadata/OpenMetadata/blob/main/ingestion/src/metadata/ingestion/source/database/usage_source.py) |
| dbt | Catalog and manifest files, "We also fetch the column level lineage through dbt" | [workflow docs](https://docs.open-metadata.org/latest/how-to-guides/data-lineage/workflow) |
| Pipeline and dashboard connectors | Each connector reports the edges its tool knows about, such as Airflow tasks or BI data sources | [lineage overview](https://docs.open-metadata.org/latest/how-to-guides/data-lineage) |
| OpenLineage | Push: `POST /v1/openlineage/lineage` and `/lineage/batch` on the server. Pull: a pipeline connector consuming OpenLineage events from Kafka or Kinesis | [`OpenLineageResource.java`](https://github.com/open-metadata/OpenMetadata/blob/main/openmetadata-service/src/main/java/org/openmetadata/service/resources/lineage/OpenLineageResource.java); [`openlineage/connection.py`](https://github.com/open-metadata/OpenMetadata/blob/main/ingestion/src/metadata/ingestion/source/pipeline/openlineage/connection.py) |
| Manual or API | UI editing, or `AddLineageRequest` with `fromEntity` and `toEntity` | [`addLineage.json`](https://github.com/open-metadata/OpenMetadata/blob/main/openmetadata-spec/src/main/resources/json/schema/api/lineage/addLineage.json) |

### 1.2 Query-log parsing: writes become lineage, reads become usage

- **Two workflows share the same query log.** "There are specific workflows (Usage & Lineage) that will use the query log information" ([lineage ingestion docs](https://docs.open-metadata.org/latest/connectors/ingestion/lineage)).
- **Lineage keeps only write statements.** For Postgres, the lineage source adds the filter `query ILIKE '%create table%as%select%' OR '%insert%into%select%' OR '%update%' OR '%merge%'` ([`postgres/lineage.py` L51–56](https://github.com/open-metadata/OpenMetadata/blob/main/ingestion/src/metadata/ingestion/source/database/postgres/lineage.py)). Usage has `filters = ""` and so takes every query ([`postgres/usage.py` L43](https://github.com/open-metadata/OpenMetadata/blob/main/ingestion/src/metadata/ingestion/source/database/postgres/usage.py)).
- **The Postgres query log is `pg_stat_statements` joined to users and databases.** It returns `usename`, `database_name`, `query_text` and `duration`, and excludes OpenMetadata's and dbt's own tagged queries ([`postgres/queries.py` L16–33](https://github.com/open-metadata/OpenMetadata/blob/main/ingestion/src/metadata/ingestion/source/database/postgres/queries.py)).
- **Attribution is by database user only.** Each `TableQuery` carries `userName`, and nothing else identifies the client ([`tableQuery.json`](https://github.com/open-metadata/OpenMetadata/blob/main/openmetadata-spec/src/main/resources/json/schema/type/tableQuery.json)). Usage stores these as **Query** entities with `users` ("users who ran this query"), `usedBy` ("users who ran the query but does not exist in OpenMetadata"), `queryUsedIn`, `triggeredBy` and `checksum` ([`query.json`](https://github.com/open-metadata/OpenMetadata/blob/main/openmetadata-spec/src/main/resources/json/schema/entity/data/query.json)). They feed the table's *Queries* tab, usage counts and joins ([usage docs](https://docs.open-metadata.org/latest/connectors/ingestion/workflows/usage)).
- **The parser.** `LineageParser` wraps `collate_sqllineage`'s `LineageRunner` and picks the best of the sqlglot, sqlfluff and sqlparse analyzers for each query ([`lineage/parser.py`](https://github.com/open-metadata/OpenMetadata/blob/main/ingestion/src/metadata/ingestion/lineage/parser.py), `_evaluate_best_parser`). It is pinned as `collate-sqllineage==2.1.8` ([`setup.py` L225](https://github.com/open-metadata/OpenMetadata/blob/main/ingestion/setup.py)).
- **Matching to entities.** The parser returns source, target and intermediate tables, column lineage and table joins. Table names are then matched to OpenMetadata entities by fully qualified name through Elasticsearch ([lineage ingestion docs](https://docs.open-metadata.org/latest/connectors/ingestion/lineage)).
- **Literal masking.** Literals are replaced by `?` with the same parsed AST before queries are stored ([`lineage/masker.py`](https://github.com/open-metadata/OpenMetadata/blob/main/ingestion/src/metadata/ingestion/lineage/masker.py)).

### 1.3 Granularity

- **Entity level.** An edge is `fromEntity` → `toEntity`, and both are generic `EntityReference`s, so tables, dashboards, pipelines and other entities can be nodes.
- **Column level.** `lineageDetails` (with `columnsLineage` and `sqlQuery`) is "provided only for table to table lineage edge" ([`entityLineage.json`](https://github.com/open-metadata/OpenMetadata/blob/main/openmetadata-spec/src/main/resources/json/schema/type/entityLineage.json)).
- **Where column lineage comes from.** It is generated for views and query-log writes by the SQL parser, and it comes from dbt and from OpenLineage column-lineage facets.

### 1.4 OpenLineage drops readers

The server mapper accepts an event only if it is of an accepted type and `!nullOrEmpty(event.getInputs()) && !nullOrEmpty(event.getOutputs())`. Otherwise it logs "Skipping OpenLineage event: filtered event type, or no inputs or outputs" ([`OpenLineageMapper.java` L94–97](https://github.com/open-metadata/OpenMetadata/blob/main/openmetadata-service/src/main/java/org/openmetadata/service/openlineage/OpenLineageMapper.java)). An application that only *reads* a dataset therefore leaves no trace in OpenMetadata's lineage, even if it emits OpenLineage.

## 2. Graph databases, Cypher and SPARQL

- **Neo4j connector (metadata only).** It was added in [#34250](https://github.com/open-metadata/OpenMetadata/pull/34250) on 2026-10-16. It is on `main` and not yet in `2.0.7-release`.
  - **Mapping.** Database → the Neo4j database. Schemas → `nodes` and `relationships`. Tables → node labels and relationship types. Columns → their properties, typed from `db.schema.nodeTypeProperties()` and `db.schema.relTypeProperties()` ([`neo4j/metadata.py`](https://github.com/open-metadata/OpenMetadata/blob/main/ingestion/src/metadata/ingestion/source/database/neo4j/metadata.py), [`neo4j/queries.py`](https://github.com/open-metadata/OpenMetadata/blob/main/ingestion/src/metadata/ingestion/source/database/neo4j/queries.py)).
  - **What it reads.** Its in-app docs say "No node or relationship data is read beyond what the schema procedures return", and the built-in `reader` role is enough ([`Neo4j.md`](https://github.com/open-metadata/OpenMetadata/blob/main/openmetadata-ui/src/main/resources/ui/public/locales/en-US/Database/Neo4j.md)).
  - **What it supports.** Its `service_spec.py` registers only a metadata source and a connection class, with no lineage or usage source. The connection schema advertises only `supportsMetadataExtraction` ([`neo4jConnection.json`](https://github.com/open-metadata/OpenMetadata/blob/main/openmetadata-spec/src/main/resources/json/schema/entity/services/connections/database/neo4jConnection.json)).
- **No Cypher or SPARQL parsing anywhere.** The only query parser is SQL (`collate-sqllineage`). No other graph-database connector appears among the database connection schemas (no Neptune, SPARQL or RDF store).
- **OpenLineage has no graph-store convention.** Its naming spec lists warehouses, catalogs, lakes, file systems, document systems, Kafka and PubSub, but no Neo4j, Neptune, SPARQL or RDF namespace ([OpenLineage naming](https://openlineage.io/docs/spec/naming)).
- **Aside, for other map tickets.** OpenMetadata `main` has an RDF layer for its *own* metadata, backed by Fuseki, with classes such as `GlossaryOntologyExporter` and `GlossaryRdfImporter` ([`service/rdf/`](https://github.com/open-metadata/OpenMetadata/tree/main/openmetadata-service/src/main/java/org/openmetadata/service/rdf)). It exports OpenMetadata's Glossary as an ontology and is not a source connector.

## 3. Could the same technique find a Knowledge Graph's Consumers?

### 3.1 What a Neo4j query log offers

Neo4j's `query.log` is an Enterprise feature ([Neo4j logging](https://neo4j.com/docs/operations-manual/current/monitoring/logging/)).

- **Settings.** `db.logs.query.enabled` takes `OFF`, `INFO` or `VERBOSE` (default `VERBOSE`). `db.logs.query.threshold` defaults to `0s`, which logs all queries. `db.logs.query.parameter_logging_enabled` defaults to `true`. `db.logs.query.obfuscate_literals` defaults to `false`, and the docs recommend `true` in production.
- **Fields per entry.** The query text and parameters, `executingUser` and `authenticatedUser`, the database, the client address, the driver and version (e.g. `neo4j-javascript/6.0.1`), transaction metadata (`annotationData`, for example an `app` key), `queryLang` and timings.
- **Format.** JSON is available through `QueryLogJsonLayout.json`, and the docs say it will become the default.

This beats OpenMetadata's Postgres source for attribution. A driver string or an `app` key in transaction metadata can tell apart two applications that share one service account; `usename` alone cannot.

### 3.2 Mapping the technique onto stetiq

| OpenMetadata step | stetiq analogue | Change needed |
|---|---|---|
| Read the query log (system table or CSV) | Read Neo4j `query.log` (JSON), or a file the user exports | Must be **read** queries. OpenMetadata keeps reads for Usage, not Lineage |
| SQL parser → tables and columns | Cypher parser → labels, relationship types and properties, matched to Ontology Concepts | No off-the-shelf piece in OpenMetadata. Needs a Cypher grammar (openCypher) or Neo4j `EXPLAIN` plans |
| `userName` → Query `users` | Client identity (driver, `app` metadata, user) → **candidate Consumer** | A heuristic: shared service accounts and gateways merge Consumers |
| Masked Query entity | Masked query template → **evidence for a Competency Question** | A query is an implementation of a question, not the question. The CQ text and id still need a person |
| Usage counts | Concepts each candidate Consumer touches → **coverage gap** against the Use Case's declared Tasks and CQs | New. OpenMetadata has no analogue |

### 3.3 Against the ADRs

- **ADR 0001 (no instance data).** Raw query-log entries *are* instance data: parameters, literal values in `WHERE` clauses, and IP addresses. To stay inside the ADR:
  - the log is read in the user's process;
  - parameters are dropped;
  - literals are masked before anything leaves, as OpenMetadata's `masker.py` does (or the user sets `obfuscate_literals=true` and `parameter_logging_enabled=false` in Neo4j);
  - only structure crosses to the core: client identity, the set of Concepts touched, masked templates, and counts.

  This matches the existing Observed Schema boundary of aggregates only.
- **ADR 0005 (the core never connects out).** Discovery has to be an edge component, shaped like the Graph Source adapter: it runs in the user's process, or the user pushes a file. OpenMetadata's own CSV fallback for unsupported sources is a precedent. A server that reads Neo4j's logs would reverse the ADR.
- **ADR 0008 (Consumer Gates are declared in the Use Case).** Discovered Consumers can only be **proposals**. Accepting one yields a new Use Case Version, written by a person. Silently adding Consumers would change which Consumer Gates run and would break the rule that the Consumer's team owns its rules.

### 3.4 Limits

- **Edition.** The Neo4j query log is Enterprise-only per the docs, so Community users get nothing from this route.
- **Invisible Consumers.** Readers that go through an API, cache, export or LLM tool layer appear only as that intermediary.
- **Weak CQ signal.** Templates show *what is asked*, not *why*. Turning them into named, stable-id Competency Questions stays a human step.
- **Consumer-side evidence still needs a Connector.** The cleaner source is a Consumer that declares itself, through stetiq's **Connector** (see `docs/specs/consumer-connector.md`) or by tagging its transactions with `app` metadata. That is opt-in, unlike log mining.

## 4. Findings that bear on stetiq's pitch

1. **OpenMetadata can now see Neo4j schemas (on `main`).** "Catalogs don't see graphs" is no longer safe to say. What it sees is a label/relationship-type → table flattening, with no Ontology Versions, Diff, Drift, Use Case or gates. It also has no usage or lineage for Cypher.
2. **OpenMetadata cannot answer "which Consumers depend on which Concepts of this KG".** Its lineage is write-driven and drops read-only OpenLineage events, and it has no usage for graph stores. stetiq's declared, versioned Use Case remains differentiated. Log-mined Consumer proposals would be a stetiq-only feature, not something to borrow from OpenMetadata.
3. **Integrate path.** If a pilot team runs OpenMetadata with the Neo4j connector, its table and column entities could, in principle, be targets for stetiq links. That is low value until pilots show OpenMetadata in LLM→KG stacks (map Notes: *Borrow first*).

Validate in pilot interviews: whether KG teams run Neo4j Enterprise with query logging on, and whether their Consumers are distinguishable by driver or `app` metadata.
