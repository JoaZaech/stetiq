# Ontology view: data and task abstraction

Munzner's nested model (*Visualization Analysis & Design*, ch. 2–4) applied to the missing network view of an Ontology. Levels: domain situation → data abstraction (what) → task abstraction (why) → idiom (how). Idioms are decided only after the what and why are settled.

## Domain situation

- **Users**: the KG engineer who owns a Knowledge Graph, *and* the casual AI / software engineer who meets an Ontology without ontology-engineering background. The view must make sense without OWL/RDF vocabulary.
- **Situation**: reviewing an Ontology Version (or a Candidate before Promotion), and orienting in an unfamiliar Knowledge Graph.
- **What is drawn**: the Ontology itself — classes, relations, attributes. Never instance data (ADR 0001).

## Scale

- Designed for ≤ ~100 classes and a few hundred Patterns, degrading through filtering and focus-on-a-Concept beyond that. Thousands of classes (SNOMED-size OWL) are out of scope.
- **Known weakness**: this is not the right design for scaling later; larger Ontologies will need aggregation or a different idiom, to be revisited.

## Task abstraction (why)

Core, in {action, target} form:

- Explore → topology: overall shape (hubs, clusters, isolated and dead-end classes).
- Browse → neighbours: what connects to a given class, in and out.
- Locate / identify → paths: whether and how one class reaches another.
- Summarize → the Ontology as a whole.
- Compare → changes: where in the structure an Ontology Diff (or other comparison) lands.

Secondary: summarize → subclass hierarchy; identify → features (deprecated, undeclared, low-fill Concepts) in context.

## Data abstraction (what)

Dataset type: a **compound network** — a directed multigraph with self-loops (the relation network) plus a tree over the same nodes (the subclass hierarchy) — with per-item attribute tables.

### Items

| Item | Source | Key |
|---|---|---|
| Node: class | `NodeType` | label |
| Link: Pattern | `Pattern(source, relationship, target)` | (source, relationship, target) |
| Link: subclass | `NodeType.parent` | (child, parent) |

Relations are not nodes: a RelationshipType with several Patterns is several links sharing a category. Inherited Patterns are derived on demand (focus, path queries), never materialized in the base dataset.

### Attributes

| Attribute | On | Type | Source |
|---|---|---|---|
| label | class, Pattern link | categorical (key) | declared |
| relationship type | Pattern link | categorical | declared |
| deprecated | class, relation | categorical (binary) | declared |
| description | class, relation | text | declared |
| properties (name, type, required) | class, relation | nested table — details on demand only, never drawn | declared |
| property count, constraints | class | quantitative, categorical | derived |
| degree (in / out), hierarchy depth | class | quantitative | derived from structure |
| instance count | class, Pattern link | quantitative | joined from an Observation against this version, optional |
| fill rate | property | quantitative, [0, 1] | joined from an Observation, optional |
| in / out degree min, max, mean | Pattern link | quantitative | joined from an Observation, optional |

The base view needs only the declared Ontology; Observed statistics are an optional join (Observations record the Ontology Version they were compared against). All stay aggregate (ADR 0001).

### Comparison

Comparing two sides yields a **union network** of both, with two derived attributes per item:

- **change kind** — categorical: added / removed / modified / unchanged.
- **severity** — ordinal: none < additive < deprecating < breaking (from the Ontology Diff).

Core pairings: Ontology Version ↔ Ontology Version, and Candidate ↔ Contract Alias. Declared Ontology ↔ Observed Schema (Conformance, Drift) reuses the same abstraction as a later layer.

## Idiom (how)

- **Base idiom**: node-link only. An adjacency matrix is the recorded escape hatch for the scaling weakness, not built now.
- **Comparison**: superimposed on the union network over one stable layout — unchanged items muted, changed items emphasized, removed items as dashed ghosts in their old position. Not juxtaposed.
- **Placement**: a Table / Map toggle (the `ViewModeToggle` pattern) in the version page's Ontology tab, Map the default, the same `?q=` search driving both. The Changes tab and the Ontology Diff Compare page get the same toggle. The tables stay as the precise lookup view.
- **Name**: "Map" — a UI label, not a domain term; avoids "graph" next to "Knowledge Graph".
- **Interactions (v1, nothing else)**:
  - Select a node or link → highlight its neighbours, fade the rest, open a details panel (description, properties, constraints, Observed statistics when present). Properties appear only here.
  - Search → locate and highlight matches.
  - Path between two selected classes → highlight shortest path(s); inherited Patterns derived here.
  - Filter → hide deprecated items, toggle subclass links.
  - Navigate → pan and zoom; no semantic zoom.
  - No editing on the canvas, no persisted free-form layout.

### Channels

| Data | Channel |
|---|---|
| severity (ordinal) | the existing `diff-*` hues, reserved for it alone |
| change kind (categorical) | mark style: added solid and emphasized, removed dashed ghost, modified outlined ring, unchanged muted |
| relationship type (categorical, often > 7 values) | text label on the link — never hue |
| subclass link | distinct style: thin grey, hollow-triangle arrowhead |
| deprecated | reduced opacity, struck-through label |
| instance count (Observation joined only) | node area, link width; uniform nodes otherwise |
| parallel links / self-loops | separate curved links / small arc |

### Layout

Deterministic (seeded) stress / force layout, computed once over the union network of the compared versions so positions stay stable — a preserved mental map. Subclass links act as springs so subclasses sit near their parents; no containment.

## Algorithm

- **Library**: `@xyflow/react` (React Flow) for rendering, `elkjs` for layout. Shortest path is a plain BFS.
- **Where**: everything here is a presentation derivation computed in the frontend from existing endpoints (`version.ontology`, the Ontology Diff). No new REST route or SDK operation (ADR 0005). Change severity comes from the core's Ontology Diff, never recomputed in the frontend.

## Validation

- **Abstraction**: 2–3 engineers, on the example Knowledge Graphs, find a class's neighbours, trace a path between two classes, and say what changed between two versions and where — faster or more correctly with Map than with Tables.
- **Idiom**: severity legible in light and dark themes; layout stable between two versions.
- **Algorithm**: layout under ~1 s at 100 classes.

## Later layers (out of v1)

- Declared Ontology ↔ Observed Schema on the same union-network abstraction (Conformance, Drift, Pending Migration).
- Competency Question overlay: highlight the Concepts and paths a Competency Question references.
- Adjacency matrix or aggregation for Ontologies beyond the scale target.
