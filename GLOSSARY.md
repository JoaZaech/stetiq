# stetiq

A DevOps platform for knowledge graph structure: it versions, evaluates and governs the ontology of a knowledge graph, the way MLflow does for models. It is the evaluation point between the upstream pipeline that produces a knowledge graph and the downstream Consumers that use it: upstream pipeline → stetiq → knowledge graph → Consumers. It evaluates what the upstream pipeline produces, gives those evaluations back to the pipeline, and manages the Ontology Versions; the pipeline itself remains the user's. Instance data stays in the graph database and is never stetiq's concern beyond reading it to observe structure.

## Language

### Structure

**Ontology**:
The structure of a knowledge graph: its Classes, Relations, Attributes and Axioms, together with the Vocabularies its Attributes draw values from, independent of any formalism (OWL, SHACL, property-graph schema).
_Avoid_: Schema (unqualified), model, TBox

**Concept**:
A single Class, Relation or Attribute of an Ontology, identified by its label across Ontology Versions; a rename is a removal plus an addition unless declared as a replacement.
_Avoid_: Element, entity, type, term

**Class**:
A kind of thing the knowledge graph holds, such as Machine or WorkOrder; a node type in a property graph.
_Avoid_: Node type (outside property-graph contexts), entity type, category

**Relation**:
A kind of directed connection between instances of Classes, such as PERFORMED_ON; a relationship type in a property graph, an object property in OWL.
_Avoid_: Edge type, relationship (unqualified), link

**Attribute**:
A kind of literal value a Class or Relation carries, such as a name or a date; a datatype property in OWL.
_Avoid_: Property (unqualified), field, column

**Axiom**:
A formal statement in an Ontology that the graph must satisfy: a subclass, a Relation's permitted endpoints and cardinality, a required Attribute, uniqueness, an Attribute's Vocabulary. stetiq reads every Axiom closed-world, as a rule checked against the graph, never as grounds for inferring new facts.
_Avoid_: Constraint (unqualified), rule, restriction, shape

**Vocabulary**:
A named, flat set of Vocabulary Values that any Attribute bound to it may take, such as the statuses of a WorkOrder; part of the Ontology and versioned with it.
_Avoid_: Enum, taxonomy, code list, lookup table

**Vocabulary Value**:
One permitted value of a Vocabulary, identified by its label, with its own Definition and Alternative Labels; deprecated and replaced like a Concept.
_Avoid_: Enum member, code, option

**Deprecation**:
Marking a Concept or Vocabulary Value as no longer to be used, optionally naming its replacement and the reason, while keeping it in the Ontology; the Ontology Version that introduces it dates it.
_Avoid_: Retirement, removal, soft delete

**Definition**:
The statement of what a Concept is and what it excludes; part of the Concept and versioned with it.
_Avoid_: Description, comment, documentation

**Alternative Label**:
Another name a Concept is known by, such as a synonym or acronym; it never identifies the Concept.
_Avoid_: Alias (an Alias points to an Ontology Version), synonym

**Declared Ontology**:
The formal structure definition a Construction Run is given as input; every Construction Run has one.
_Avoid_: Target schema, spec

**Observed Schema**:
The Ontology as it actually appears in a Graph Source, together with its aggregate statistics (counts per class and relation, cardinalities, attribute fill rates, and the capped set of values each Vocabulary-bound Attribute takes), derived from but never containing instance data.
_Avoid_: Inferred ontology, actual schema

**Conformance**:
The degree to which an Observed Schema satisfies its Declared Ontology's Axioms.
_Avoid_: Compliance, validity

**Knowledge Graph**:
A named, long-lived lineage of Ontology Versions, e.g. "customer-support-kg".
_Avoid_: Project, experiment, graph (unqualified)

**Steward**:
The person named on a Knowledge Graph as responsible for its Ontology's health: watching Drift and keeping Definitions and Competency Questions current. A name only; it grants no permission.
_Avoid_: Owner (unqualified), maintainer

**Authority**:
The person or function named on a Knowledge Graph as the one who decides changes to its Ontology. A name only; edit permission comes from API Tokens.
_Avoid_: Approver, admin, owner (unqualified)

**Ontology Version**:
An immutable snapshot of a Knowledge Graph's Ontology, numbered 1, 2, 3… within its Knowledge Graph; what changed since another version is told by their Ontology Diff, not by the number.
_Avoid_: Revision, release, graph version

**Ontology Diff**:
The structural difference between two Ontology Versions, with each change classed as cosmetic (only Definitions or Alternative Labels change), additive, deprecating or breaking.
_Avoid_: Changeset, delta

**Consumer impact**:
Which Consumers an Ontology Diff hits, followed from each changed Concept through the Competency Questions that need it to their Tasks: **affected** by a breaking change, **will be affected** by a deprecating one, and **unknown** when a question states neither a Concept mapping nor a query; a Task or Consumer takes its most severe level.
_Avoid_: Blast radius, downstream impact

**Graph Source**:
A scope within an external graph database (a database, optionally narrowed by label or namespace) bound to one Knowledge Graph, which stetiq reads but never owns.
_Avoid_: Graph store, backend

### Evaluation

**Evaluator**:
A pluggable measurement applied to an Ontology that produces one or more metrics, e.g. the share of Concepts traced to a Competency Question, Competency Questions broken by a removed Concept, or Concepts missing a Definition.
_Avoid_: Metric (for the measurement itself), check

**Competency Question**:
A domain question the knowledge graph must be able to answer, used to judge an Ontology against the Tasks it serves; one question may serve several Tasks. Identified by an id that is stable across Use Case Versions, so changing the id is a removal plus an addition.
_Avoid_: Test query, requirement

**Use Case**:
What a Knowledge Graph exists for: the Consumers that use it, the Tasks they perform with it, and the Competency Questions those Tasks need answered; versioned independently of the Ontology.
_Avoid_: Scenario, goal

**Consumer**:
Anyone or anything that uses a Knowledge Graph downstream, of whatever kind (an application, an agent, a dashboard, a team), declared in a Use Case; it depends on the Concepts its Tasks need and has to change when those Concepts change.
_Avoid_: Client, subscriber, downstream app, persona, user

**Task**:
A piece of work one Consumer performs with a Knowledge Graph, such as triaging breakdowns, expressed by the Competency Questions it needs answered.
_Avoid_: Job, purpose, use case (for a single task)

**Use Case Version**:
An immutable snapshot of a Knowledge Graph's Use Case; adding, changing or removing a Consumer, Task or Competency Question yields a new one, and results stay tied to the version they were judged against.
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
_Avoid_: Policy, check, threshold, input gate

**Consumer Gate**:
A rule, for one Consumer, over Observed Schema statistics, Conformance, the Ontology Diff and executed Competency Question results that must hold for that Consumer to take an Ontology Version; stetiq evaluates it, the Consumer's Connector enforces it.
_Avoid_: Output gate, release gate, downstream gate

**Connector**:
What sits at a Consumer's edge and links it to stetiq: through it the Consumer learns of Ontology changes that affect its Tasks and enforces its Consumer Gate.
_Avoid_: Integration, webhook, plugin, adapter

**Gate Preview**:
Evaluating a Knowledge Graph's most recently used Gates against a Construction Run or Ontology Version without recording the outcome; Promotion's audit never counts it.
_Avoid_: Dry run, simulated gate, gate check

**Drift**:
A divergence, found by an Observation, between a Graph Source's Observed Schema and the Contract Alias's Ontology Version; it raises an alert unless it is a Pending Migration, and never creates a new Ontology Version by itself.
_Avoid_: Schema change, deviation

**Pending Migration**:
Drift that the Ontology Diff, from the last Contract Alias version the Graph Source was observed to conform to up to the current one, explains, because the Graph Source has not yet caught up with a Promotion; it is shown but raises no alert until a grace period ends, after which it becomes ordinary Drift.
_Avoid_: Expected drift, migration (unqualified)

**Adoption**:
Creating a Candidate from the Contract Alias's Ontology Version plus Concepts an Observation found that the user selected: selected undeclared Concepts are added, selected vanished Concepts are deprecated, never removed.
_Avoid_: Import, sync, reverse-engineering

**API Token**:
A secret that authenticates one user to a stetiq server and grants *read* or *edit* permission per Knowledge Graph; the audit log records its user as the actor. Local mode has none.
_Avoid_: API key, password, session
