# Market landscape: who evaluates LLM→KG output and Ontologies?

Research for [#136](https://github.com/JoaZaech/stetiq/issues/136), part of the map [#135](https://github.com/JoaZaech/stetiq/issues/135). Gathered 2026-11-01 from first-party docs, repositories and papers. Terms follow `GLOSSARY.md`.

**Question.** Who already evaluates or governs the output of LLM-based Knowledge Graph extraction, or the Ontology of a Knowledge Graph? For each tool: what it judges, against what reference, upstream or downstream, open source or commercial. Where is stetiq's gap?

"Upstream" means the tool judges what the extraction pipeline produced (the graph or its structure). "Downstream" means it judges what a Consumer gets out of the graph (answers, retrieval).

## Summary table

| Tool | Judges | Reference | Side | License |
|---|---|---|---|---|
| Neo4j LLM Graph Builder | Chat answers over the built graph | Retrieved context, optional reference answer | Downstream | Apache-2.0 (Neo4j Labs, unsupported) |
| neo4j-graphrag-python KG builder | Nothing scored. It prunes extracted nodes, edges and properties outside a schema | A user or LLM-extracted schema | Upstream (filter, not evaluator) | Apache-2.0 |
| Microsoft GraphRAG + BenchmarkQED | RAG answers, side by side | LLM judge, optional ground truth | Downstream | MIT |
| Ragas | RAG, agent and SQL outputs | Context, reference answers, rubrics | Downstream | Apache-2.0 |
| LangSmith (also Arize, Braintrust and similar) | LLM app runs and traces | Datasets, LLM judge, heuristics, humans | Downstream, or per extraction call | Commercial SaaS (SDK MIT) |
| SHACL engines (pySHACL, TopBraid EDG, Stardog …) | Instance data | A hand-written shapes graph | Upstream, per data graph | pySHACL Apache-2.0; EDG and Stardog commercial |
| TopBraid EDG workflows | Ontology and taxonomy edits | SHACL conditions on workflow transitions | Ontology governance, human-authored | Commercial |
| Open Ontologies | OWL ontology changes: diff, drift, risk | The previous ontology version, SPARQL monitors | Ontology governance | MIT (plus hosted commercial platform) |
| Text2KGBench and similar benchmarks | Extracted triples | Gold triples, the given ontology, source text | Upstream, offline research benchmark | Open dataset and scripts |

## Per tool

### Neo4j LLM Graph Builder

Turns documents into a Neo4j graph with an LLM, with an optional custom or saved schema to guide extraction ([repo](https://github.com/neo4j-labs/llm-graph-builder)). It has no measure of extraction quality. Its only quality numbers are in chat: `POST /metric` computes Ragas `faithfulness`, `answer_relevancy` and `context_entity_recall`, and `POST /additional_metrics` computes `RougeScore` and `SemanticSimilarity` against a user-given reference answer ([score.py](https://github.com/neo4j-labs/llm-graph-builder/blob/main/backend/score.py), [ragas_eval.py](https://github.com/neo4j-labs/llm-graph-builder/blob/main/backend/src/ragas_eval.py)). Its other "quality" features are clean-up steps: duplicate-node matching by similarity threshold and an LLM graph clean-up pass. Apache-2.0. It is a Neo4j Labs experiment, outside Neo4j's supported products.

**Judges:** answers to one chat question. **Reference:** retrieved context and an optional reference answer. **Side:** downstream, ad hoc. There is no Ontology versioning and nothing tracked over time.

### neo4j-graphrag-python (`SimpleKGPipeline`)

Neo4j's supported Python package. A schema guides extraction, and the LLM "may generate additional node labels, relationship types, or properties" outside it. The flags `additional_node_types`, `additional_relationship_types`, `additional_patterns` and `additional_properties` (set to `False`) and `EXISTENCE` constraints prune whatever falls outside the schema. With `schema="EXTRACTED"`, the LLM derives a schema from the text first ([KG builder guide](https://neo4j.com/docs/neo4j-graphrag-python/current/user_guide_kg_builder.html)). It produces no quality report, and failed chunks are ignored by default.

**Judges:** nothing. It silently drops output that does not conform. **Reference:** the schema of one run. **Side:** upstream, inside the data path. The schema is not versioned, and nobody learns how much was pruned.

### Microsoft GraphRAG and BenchmarkQED

GraphRAG extracts entities, relationships and claims, and recommends prompt tuning. Its docs describe no evaluation of the extracted graph and no schema checks ([docs](https://microsoft.github.io/graphrag/)). The evaluation companion, BenchmarkQED, judges **RAG answers**. Its AutoE component asks an LLM judge to compare answer pairs on relevance, comprehensiveness, diversity and empowerment, and on correctness and completeness when ground truth exists. AutoQ synthesizes the queries ([repo](https://github.com/microsoft/benchmark-qed), [MSR blog](https://www.microsoft.com/en-us/research/blog/benchmarkqed-automated-benchmarking-of-rag-systems/)). Both are MIT.

**Judges:** answer quality of whole RAG systems. **Reference:** an LLM judge and optional ground truth. **Side:** downstream. It does not look at the graph itself.

### Ragas

Metrics for RAG (context precision and recall, faithfulness, response relevancy, context entities recall), agents and tools, SQL, string comparison, and rubric-based LLM judging ([metrics](https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/)). It builds a knowledge graph internally, but only as a tool for **generating test questions** from documents, not as something it evaluates ([testset generation](https://docs.ragas.io/en/stable/concepts/test_data_generation/rag/)). Apache-2.0.

**Judges:** LLM outputs per sample. **Reference:** context, reference answers, rubrics. **Side:** downstream. It has no notion of an Ontology.

### LangSmith and other LLM-eval or observability platforms

LangSmith evaluates application runs: offline against datasets with optional reference outputs, online on production traces without references. It uses code heuristics, LLM-as-judge with or without a reference, pairwise comparison and human review ([evaluation concepts](https://docs.langchain.com/langsmith/evaluation-concepts)). The platform is commercial SaaS; the SDK is MIT. Arize Phoenix, Braintrust, Galileo and similar tools sit in the same category.

**Judges:** a single LLM call or chain output. **Reference:** a dataset, a judge or a heuristic. **Side:** these tools can point at the extraction call (for example, "is this JSON valid against a schema", "do the triples match the gold set"), but each output is a separate text sample. They see no aggregated graph structure, Ontology, Ontology Version or Consumer.

### SHACL engines (pySHACL, TopBraid, Stardog, GraphDB …)

SHACL validates a **data graph** against a **shapes graph** and returns a validation report whose `sh:conforms` is true only when there are no results ([W3C SHACL](https://www.w3.org/TR/shacl/)). `sh:closed` restricts nodes to their declared properties. pySHACL is Apache-2.0; triple stores ship commercial engines.

**Judges:** instance data, node by node. **Reference:** hand-written shapes. **Side:** upstream, as a pass/fail on the data. It reads instance data (stetiq's ADR 0001 rules that out), has no statistics or trend over time, has no notion of LLM extraction, and does not ask what the graph is *for*. This is the closest prior art to stetiq's Conformance.

### TopBraid EDG (TopQuadrant)

A commercial ontology, taxonomy and data-governance platform. Asset types are defined in SHACL, and edits are checked for conformance. **Workflows** gate change management: each state transition (for example to "Approved") can carry SHACL conditions the data must satisfy, with roles, voting, approvals and publication ([validation](https://archive.topquadrant.com/?p=15350), [workflows](https://archive.topquadrant.com/?p=15390), [9.2 release notes](https://topquadrant.com/release-note/9-2)). The claims come from vendor pages.

**Judges:** human-authored edits to an ontology or vocabulary. **Reference:** SHACL rules and governance roles. **Side:** ontology governance for curated, enterprise-modelled ontologies. It is not aimed at an LLM pipeline producing a graph, and it has no per-Consumer fitness check.

### Open Ontologies (fabio-rovai/open-ontologies)

The nearest neighbour on Ontology governance. It is an MIT Rust CLI and MCP server (about 2.7k stars) with a Terraform-style lifecycle ([repo](https://github.com/fabio-rovai/open-ontologies), [lifecycle](https://github.com/fabio-rovai/open-ontologies/blob/main/docs/lifecycle.md)):

- **plan** diffs the current OWL ontology against a proposed one and reports added and removed terms, a "blast radius" and a low/medium/high risk score, plus conservativity and logic checks.
- **enforce** runs design-pattern packs and SPARQL rules.
- **apply** writes the delta. `migrate` mode adds equivalence bridges "for consumers".
- **monitor** runs SPARQL watchers with `notify`, `block_next_apply` and `auto_rollback` actions.
- **drift** compares ontology versions, detects renames with Jaro-Winkler similarity, and reports drift velocity.

A hosted commercial platform (tesseractsemantics.com) sits on top.

**Judges:** ontology changes, which are authored by hand or by an assistant. **Reference:** the previous version and logic rules. **Side:** ontology governance. Its blast radius is not traced to named Consumers or their Tasks and Competency Questions, and it does not frame its input as the output of an LLM extraction pipeline or compare the Observed Schema with the Declared Ontology.

### Academic ontology-drift and diff tools

DynDiff ([J. Biomed. Semantics 2023](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC10537977/)), OntoDrift (Capobianco et al., 2020) and COnto-Diff compute and classify differences between ontology versions or measure semantic drift. They are research methods for curated (often biomedical) ontologies, with no pipeline or Consumer context.

### Benchmarks: Text2KGBench and Text2KGBench-LettrIA

Text2KGBench (ISWC 2023) scores ontology-guided extraction from text with seven metrics covering fact-extraction accuracy (against gold triples), **ontology conformance** (against "the given ontology (concepts, relations, domain/range constraints)") and hallucination (against the source sentences) ([arXiv 2308.02357](https://arxiv.org/abs/2308.02357)). LettrIA's refined version fixes annotation and ontology errors ([CEUR-WS Vol-4041](https://ceur-ws.org/Vol-4041/paper3.pdf)). These benchmarks validate stetiq's upstream question (conformance plus hallucination), but they are offline, one-shot benchmarks on fixed datasets, not tooling for a user's own pipeline and Ontology.

## Where the field splits

1. **Downstream answer evaluators** (Ragas, BenchmarkQED, LangSmith, LLM Graph Builder's chat metrics) score answers and treat the graph as a black-box retriever. They tell you *that* answers got worse, not *which part of the Ontology* caused it.
2. **Upstream structure enforcers** (SHACL engines, neo4j-graphrag pruning) check or filter instance data against a fixed schema, per run, with no statistics over time and no versioning.
3. **Ontology governors** (TopBraid EDG, Open Ontologies, diff and drift research) version and gate *human-authored* ontology change. Their notion of impact is logical consequence or risk score, not "which Consumer's Tasks break".
4. **Benchmarks** (Text2KGBench) measure the right upstream things (conformance, hallucination), but offline, on someone else's data.

No tool links all four.

## stetiq's gap

**No tool sits beside an LLM extraction pipeline and judges its KG output both against the Declared Ontology (a Gate on the Observed Schema's Conformance and statistics, tracked across runs as Drift) and against what each named Consumer needs (a Consumer Gate: its Tasks' Competency Questions traced to Concepts), with the Ontology versioned in between, so that an Ontology Diff can be followed to the Consumers it affects.**

In short, stetiq ties answer-level evals (which never see structure) to ontology governance (which never sees the pipeline or the Consumers). Concretely, none of the surveyed tools:

- treats the **LLM pipeline's output structure** as the thing that drifts, as opposed to hand edits to an ontology or answer quality;
- evaluates from **aggregate structure only** (the Observed Schema), without holding instance data;
- models **Consumers → Tasks → Competency Questions → Concepts**, so that a change or a drop in Conformance is reported as *which Consumer is affected*, not as a generic risk score or an answer-quality dip.

The closest competitors to watch are **Open Ontologies** (versioning, drift, blast radius, MIT, with traction) and **TopBraid EDG** (governance workflows gated by SHACL). A pitch should place stetiq against them as "for LLM-built graphs, judged by their Consumers", not as a better ontology versioner.

## Caveats

- Open Ontologies' blast-radius definition and TopBraid's capabilities come from first-party but marketing-style pages. Neither was run.
- The individual Text2KGBench metric definitions were not read from the PDF. Only the abstract's three categories are cited.
- Commercial LLM-eval platforms other than LangSmith were not individually checked. They are assumed to be in the same category from their positioning.
