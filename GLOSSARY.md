# stetiq

A DevOps platform for knowledge graph structure: it versions, evaluates and governs the ontology of a knowledge graph, the way MLflow does for models. Instance data stays in the graph database and is never stetiq's concern beyond reading it to observe structure.

## Language

### Structure

**Ontology**:
The structure of a knowledge graph: its classes, relations, attributes, hierarchy and constraints, independent of any formalism (OWL, SHACL, property-graph schema).
_Avoid_: Schema (unqualified), model, TBox

**Concept**:
A single class, relation or attribute of an Ontology, identified by its name or IRI across Ontology Versions; a rename is a removal plus an addition unless declared as a replacement.
_Avoid_: Element, entity, type

**Declared Ontology**:
The formal structure definition a Construction Run is given as input; every Construction Run has one.
_Avoid_: Target schema, spec

**Observed Schema**:
The Ontology as it actually appears in a Graph Source, together with its aggregate statistics (counts per class and relation, cardinalities, attribute fill rates), derived from but never containing instance data.
_Avoid_: Inferred ontology, actual schema

**Conformance**:
The degree to which an Observed Schema matches its Declared Ontology.
_Avoid_: Compliance, validity

**Knowledge Graph**:
A named, long-lived lineage of Ontology Versions, e.g. "customer-support-kg".
_Avoid_: Project, experiment, graph (unqualified)

**Ontology Version**:
An immutable snapshot of a Knowledge Graph's Ontology.
_Avoid_: Revision, release, graph version

**Ontology Diff**:
The structural difference between two Ontology Versions, with each change classed as cosmetic, additive, deprecating or breaking. A cosmetic change touches only documentation (only a description changes) and ranks below additive.
_Avoid_: Changeset, delta

**Graph Source**:
A scope within an external graph database (a database, optionally narrowed by label or namespace) bound to one Knowledge Graph, which stetiq reads but never owns.
_Avoid_: Graph store, backend

### Evaluation

**Evaluator**:
A pluggable measurement applied to an Ontology that produces one or more metrics.
_Avoid_: Metric (for the measurement itself), check

**Competency Question**:
A domain question the knowledge graph must be able to answer, used to judge an Ontology against its Use Case; identified by an id that is stable across Use Case Versions, so changing the id is a removal plus an addition.
_Avoid_: Test query, requirement

**Use Case**:
The problem a Knowledge Graph exists to solve, expressed as a set of Competency Questions and tasks, versioned independently of the Ontology.
_Avoid_: Scenario, goal

**Use Case Version**:
An immutable snapshot of a Knowledge Graph's Use Case; adding, changing or removing a Competency Question yields a new one, and results stay tied to the version they were judged against.
_Avoid_: Revision, question set

**Construction Run**:
One execution of the user's extraction workflow against a Declared Ontology; recorded as provenance, not the primary subject of evaluation. When it introduces new concepts, it is linked to the new Ontology Version it gave rise to.
_Avoid_: Job, pipeline run, build run, experiment

**Construction Entry Point**:
The user-declared command stetiq can invoke to perform a Construction Run; stetiq starts it but never knows what it does inside.
_Avoid_: Pipeline, job, ingestion

### Control

**Alias**:
A named, movable pointer to one Ontology Version within a Knowledge Graph, e.g. `production` or `staging`.
_Avoid_: Stage, environment, tag

**Contract Alias**:
The Alias (by default `production`) whose Ontology Version Construction Runs consume as their Declared Ontology and Drift is measured against.
_Avoid_: Production stage, live ontology

**Candidate**:
An Ontology Version no Alias has pointed to yet, typically created by an evolving Construction Run.
_Avoid_: Draft, proposal

**Promotion**:
Moving an Alias to an Ontology Version; it is not blocked by Gates, but the audit records whether the version's latest Gate result passed.
_Avoid_: Release, deploy

**Observation**:
Capturing a Graph Source's current Observed Schema, either at the end of a Construction Run or on demand between runs.
_Avoid_: Scan, crawl, sync

**Evolution Mode**:
A Knowledge Graph's setting for Construction Runs that introduce new Concepts: *strict* fails the run, *evolving* yields a candidate Ontology Version.
_Avoid_: Schema mode, open/closed world

**Gate**:
A rule, defined in the user's repository, over Evaluator results, Conformance or the Ontology Diff that must hold for a CI check to pass.
_Avoid_: Policy, check, threshold

**Gate Preview**:
Evaluating a Knowledge Graph's most recently used Gates against a Construction Run or Ontology Version without recording the outcome; Promotion's audit never counts it.
_Avoid_: Dry run, simulated gate, gate check

**Drift**:
A divergence, found by an Observation, between a Graph Source's Observed Schema and the Contract Alias's Ontology Version; it raises an alert, never a new Ontology Version.
_Avoid_: Schema change, deviation

**API Token**:
A secret that authenticates one user to a stetiq server and grants *read* or *edit* permission per Knowledge Graph; the audit log records its user as the actor. Local mode has none.
_Avoid_: API key, password, session
