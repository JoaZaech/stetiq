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
- **Placement**: a Table / Map toggle (the `ViewModeToggle` pattern) in the version page's Ontology tab, Map the default, the same `?q=` search driving both. The Changes tab and the Ontology Diff Compare page get the same toggle, also Map the default, with the Diff's list at `?view=table`. The tables stay as the precise lookup view.
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

## Round 2: after the first build

Feedback from using the v1 Map on the example Knowledge Graphs, with the level of the nested model each finding sits at:

- **Task: summarize → changes was missing.** The comparison Map showed *where* a change landed but never *what* changed. Attribute-level changes are invisible on the canvas, and documentation-only edits drowned the real ones (city-transit v2→v3: two breaking attribute renames, eight relation description edits, so every link turned green).
- **Task: search mixed two tasks.** Locating a Concept by name and exploring where a term appears shared one full-text box, so `Bin` lit up for "Warehouse" through its description and its `warehouse` attribute, with no reason shown.
- **Idiom: link labels were unreadable**, drawn under nodes and links, with fit-to-view shrinking text below legibility.
- **Idiom: the Table did not read like a database.**

Decisions:

- **Change summary.** A comparison always shows a summary panel beside the Map: a headline count per level ("2 breaking · 2 additive · 8 documentation-only"), then changes grouped by Concept and sorted by severity. It is linked both ways: hovering or clicking an entry focuses its Concept on the Map, and selecting on the Map scrolls to its entry.
- **Documentation-only changes** (only a description differs) are their own quiet level: a small neutral dot, no severity hue, no emphasis, collapsed to one line in the summary. They are the Diff's *cosmetic* classification (#97), which ranks below additive; the UI keeps calling them documentation-only.
- **Changed attributes on the canvas, in comparisons only.** A changed class expands to list just its changed attributes, diff-style (`− wheelchairBoarding`, `+ wheelchair_boarding`); unchanged attributes stay hidden. The plain Map keeps attributes off the canvas — a narrow exception to details-on-demand, because in a comparison the change is the detail being asked for.
- **The Table** keeps its three sections (classes, relations, attributes) and their row structure — relations stay one row per relation with its Patterns, not foreign keys — but gains grid behaviour, grouping, purpose and connection back to the Ontology:
  - **Layout**: the sections stay stacked on one page, each collapsible, under a sticky jump bar with counts (`Classes 8 · Relations 8 · Attributes 34`).
  - **Purpose**: each section opens with one line, in glossary words, saying what it means in the Ontology (classes are the kinds of things stored, indented ones are subclasses that inherit; relations say how classes connect, each Pattern which class may link to which; attributes are the fields stored on a class or relation).
  - **Grid behaviour**: sortable columns, a filter per column (text for names, a value list for type and kind, a toggle for required, unique and deprecated), a row count ("12 of 34"), full-text search across the grid, type names in monospace. Sort, filters and search live in the URL.
  - **Grouping**: attributes are grouped by owner by default — collapsible groups headed by the owner, its kind, its superclass and its attribute count — with inherited attributes listed under each subclass and marked ("from Person"). A Group-by control switches between Owner, Type and None.
  - **Columns** (bold visible by default, the rest in the column picker):
    - Classes: **Class**, **Superclass**, **Attributes** (own count, inherited count in parentheses), **Outgoing** and **Incoming** (relation names as links, `HAS_TRIP → Trip`), **Constraints**, **Description**, Deprecated.
    - Relations: **Relation**, **Patterns** (one per line, each class name a link), **Attributes** (count, linking to its group), **Description**, Deprecated.
    - Attributes: **Owner**, Owner kind, **Attribute**, **Type**, **Required**, **Unique**, Inherited from, **Description**.
  - **Connection**: every class and relation name in any section is a link that scrolls to and highlights its row; each row has "Show on Map"; the selection is shared between Table and Map. A mini Map in the Table is left for later.
  - **Comparison Table**: the Diff list on the Changes tab and the Compare page becomes the same kind of grid — Concept, Concept kind, Change (added, removed, changed, deprecated), Severity (documentation-only its own value), Detail — with the same sorting, filters and "Show on Map", and documentation-only changes filtered out by default.
- **Search is labels first.** Typing shows a results list that separates name matches from other matches, each with its reason ("`Bin`: description mentions 'warehouse'; attribute `warehouse`"). Picking a result selects and centers it. The Map highlights only name matches while typing; Table filtering keeps full-text matching.
- **Link labels**:
  - drawn in a top layer above nodes and links, on a solid background pill
  - the layout leaves room for labels, and parallel links' labels are staggered
  - below a zoom threshold, labels are hidden except on the selected or focused neighbourhood and on changed links in a comparison
  - fit-to-view never zooms out below readable text
- **Shipping.** PR #74 goes back to draft; this round lands as new sub-tickets of #62 on the same branch, and the Map merges only once it is right.

## Round 3: screen space and legibility

Feedback from the comparison Map (city-transit v2→v3, OPERATES selected): it looked cramped and disorganized. Findings, by Munzner's principles:

- **Too many views side by side.** The change summary, canvas and details panel sat next to each other, and the summary and details both described the selected Concept. Summary entries put name, kind and badge on one line, so long names broke mid-word (`HA / S_S / TOP`).
- **Repeated encoding.** Level was stated by a badge, again in each statement ("(documentation-only)") and twice more in details.
- **Two channels, one legend.** Change kind (mark style) and severity (hue) shared one 8-item legend, which with the filters covered the top of the canvas.
- **Focus hid the task.** Focus+context faded the changed Concepts (the breaking Trip and Stop) along with everything else.
- **Wasted canvas.** One expanded class spread the whole layout by a single global factor; class names truncated; fit-to-view rendered node text at ~10px.

Decisions (comparison Map first; the plain Map takes the shared parts):

- **One side panel.** A single right-hand panel replaces the summary and details panes. It shows the change summary with nothing selected, a Concept's details or the shortest path once something is selected, with a "← All changes" back link. It collapses to a thin rail showing the headline counts. On the plain Map it appears only for a selection.
- **Summary partitioned by level.** Sections Breaking, Deprecating, Additive, then collapsed Documentation-only, each heading in its severity colour once. An entry is the Concept's name on its own full-width line (wrapping at `_`, never mid-word), its kind in small text, then its statements. A statement names its level only when it differs from its section's. No per-entry badges.
- **Documentation-only changes show their text.** Details show Before and After descriptions with a word-level diff. The summary entry previews the new description in one line. Both come from the two Ontologies the comparison already loads.
- **Legend split by channel.** The severity key is the panel's headline counts, each drawn as its own swatch. Only a one-row change-kind key (added, removed, modified, unchanged) stays on the canvas, bottom-left by the zoom controls.
- **Filters leave the canvas.** Hide deprecated and Hide subclass links move to the header row beside the Table / Map toggle.
- **Changed Concepts stay as context.** Under focus, changed Concepts outside the neighbourhood stay readable (~60%, severity outline visible); only unchanged ones fade fully.
- **Open on the changes.** A comparison Map first fits to its changed Concepts; fit-all stays one click away: Fit view frames the whole Map, without the text floor, which is for the first view.
- **Text floor.** The first view never zooms out below 0.85 (node names ≥ ~12px); a Map too big for it is left to be panned.
- **Class names are never truncated.** Class nodes grow to fit their name in monospace measurement, like link label pills; no ellipsis, no wrapping.
- **Local overlap removal.** The global spread factor is replaced by ELK's SPOrE overlap removal after stress, which moves nodes only as far as needed to clear overlaps and keeps their order. Still one deterministic layout over the union network, so stable between versions.
- **Search results in the same panel.** Search results are a state of the one panel, not a pane on the left. Picking a result opens its details, with "← Results" back.
- **Validation.** On city-transit v2→v3: no Concept name breaks mid-word, in the panel or on the canvas; both breaking classes stay visible with OPERATES selected; the first view frames the changes at readable text size; a documentation-only change can be read without the Table.
- **Shipping.** A spec, then four sub-tickets of #62: the single side panel (with search, path, collapse rail and count legend); the summary by level and the documentation-only diff; the canvas changes (filters, change-kind key, context fading, fit-to-changes, zoom floor); and the layout (sized class nodes, SPOrE).

## Later layers (out of v1)

- Declared Ontology ↔ Observed Schema on the same union-network abstraction (Conformance, Drift, Pending Migration).
- Competency Question overlay: highlight the Concepts and paths a Competency Question references.
- Adjacency matrix or aggregation for Ontologies beyond the scale target.
