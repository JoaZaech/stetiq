# Using the web UI

The web UI shows every Knowledge Graph you can read: its Ontology Versions, Construction Runs, Use Case, Observations and Promotions. It is also where you make the governance edits that don't belong in code: promoting an Ontology Version, editing a Knowledge Graph's description and changing its Competency Questions.

Open it with `stetiq ui` (local mode, see [Getting started](./01-getting-started.md#open-the-web-ui)) or at `/ui` on a stetiq server, where you sign in with an API Token (see [Server and API Tokens](./05-server-and-api-tokens.md)). The words used here are explained on the [Concepts](./02-concepts.md) page.

## Finding your way around

The web UI opens on **Home**: a *Getting Started* block whose cards open the guide pages for each step of the workflow (collapse it once you know your way, and it stays collapsed in that browser), and your five most recently modified Knowledge Graphs, with **View all** leading to the full list. The stetiq logo at the top of the sidebar always leads back to Home.

The sidebar looks the same on every page:

- **Home**.
- **The Knowledge Graph switcher**: shows the Knowledge Graph you are in, or *Select a Knowledge Graph*. Click it to see every Knowledge Graph you can read, with a check on the current one; type to search by name, and pick one with the mouse or the arrow keys and Enter. Switching keeps you in the same section: from *support*'s Construction Runs you land on *billing*'s Construction Runs. From a detail or compare page you land on that section's list, since the ids belong to the other Knowledge Graph. **All Knowledge Graphs** at the bottom opens the full list at `/ui/kg`. With the sidebar collapsed to icons, hover the switcher to see the Knowledge Graph's name.
- **The sections**: Ontology Versions, Construction Runs, Use Case, Observations and Promotions. Inside a Knowledge Graph they lead to its sections. Elsewhere (Home, Settings, Help, the list) they lead into the Knowledge Graph you last opened in this browser. Until you have opened one, or if it no longer exists, they are greyed out with a *Select a Knowledge Graph first* tooltip.
- **Help**: this guide.
- **Settings**: the theme (light, dark or system) and your access. In local mode, Access says every Knowledge Graph is editable and names the user your changes are recorded as. On a server, it shows who you are signed in as, your grants (*read* or *edit* per Knowledge Graph, `*` meaning all of them) and a **Sign out** button.

Breadcrumbs at the top of each page lead back up, e.g. from v3 of *support* to *Ontology Versions*, *support* and *Knowledge Graphs*. Pages, searches, filters, chosen columns and compare views live in the URL, so you can share what you are looking at by copying the address.

## What needs edit access

Some controls change a Knowledge Graph, and they need the *edit* permission on it:

| Action | Where |
| --- | --- |
| **Edit description** | The header of every Knowledge Graph section |
| **Promote** | An Ontology Version's page |
| **Add Competency Question** | The Use Case section |
| Edit and remove a Competency Question | The row of each Competency Question in the Use Case section |

Without *edit*, these controls stay visible but disabled, with a *Needs edit access* tooltip. Everything else in the UI is read-only. In local mode every Knowledge Graph is editable. The server checks every change too, so a disabled button is a convenience, not the protection.

## The Knowledge Graphs list

The Knowledge Graphs page (`/ui/kg`) lists every Knowledge Graph you can read, with:

- **Contract Alias version**: the Ontology Version its Contract Alias points to.
- **Latest version**: its newest Ontology Version.
- **Last run**: the status of its newest Construction Run (Running, Finished or Failed), or *No runs*.
- **Last modified**: when it last changed.

Click a column header to sort, and type in **Search by name** to filter. Click a name to open the Knowledge Graph. If there are none yet, the page shows how to create one from the Python SDK (see [Python SDK](./03-python-sdk.md)).

## Inside a Knowledge Graph

A Knowledge Graph opens on its Ontology Versions. Every section starts with the same header: the Knowledge Graph's name, its description (written in markdown), its Evolution Mode (*strict* or *evolving*) and its Contract Alias with the version it points to, e.g. `production → v3`.

**Edit description** (needs edit access) opens a markdown editor with a **Write** and a **Preview** tab. Saving shows the new description to everyone who can read the Knowledge Graph.

### Ontology Versions

The section lists every Ontology Version, newest first, with its origin, when it was created and the Aliases pointing to it. The Contract Alias's chip is highlighted with a star, and an Ontology Version no Alias has pointed to yet is marked **Candidate**.

- **Columns** adds a column per Evaluator metric.
- **Table** / **Chart** switches to one chart per Evaluator metric across versions, with a search box to find a metric.

**Comparing two versions.** Tick two rows and click **Compare** to see the Ontology Diff from the older to the newer version. Any two versions can be compared, not only neighbours. The Compare page works like the [Changes tab](#the-changes-tab): it opens on a **Map** of both versions laid over each other, and the **Table / Map** toggle switches to the Diff as a grid.

**An Ontology Version's page.** Click a version number to open it. It shows the version's Aliases and three tabs:

- **Overview**: its number, origin, content hash (with a copy button), when it was created and, for a version produced by a Construction Run, a link to that run. Next to these, its Evaluator results (Evaluator, metric, value and the Use Case Version it was judged against) and its latest Gate result: *Passed*, *Failed* (naming the Gates that failed) or *None*.
- **Ontology**: the version's Concepts, on a Map or in a Table. See [The Ontology tab](#the-ontology-tab).
- **Changes**: the Ontology Diff from the previous version. v1 has nothing to compare with. See [The Changes tab](#the-changes-tab).

#### The Ontology tab

The tab opens on a **Map**: each class is a box, wide enough for its whole name, and each pattern an arrow from one class to another, labelled with its relation. Two relations between the same classes are two separate arrows, and a relation from a class to itself is a loop. Drag to pan, and scroll or use the **+**/**−** buttons to zoom. The Map never opens smaller than its relation names can be read: a larger Ontology opens part in view, for you to pan. The fit view button frames the whole Map, zooming out as far as it takes. Zoomed out further, relation names are hidden, except on what you have selected and, when comparing, on the arrows that changed; zoom back in to see them all. **Hide deprecated** and **Hide subclass links**, in the header row beside the **Table / Map** toggle, take those off the Map.

**Selecting.** Click a class to highlight what it connects to and open its details in the panel on the Map's right: description, superclass, attributes (those it inherits are marked with the class they come from) and constraints. Click an arrow for its relation's description and attributes. With a class selected, shift-click another to highlight every shortest path between them, relations taken either way round and including those a class inherits from its superclass; the panel then shows the **Shortest path**, listing each path, or says that no path connects them. Press Escape, click the empty canvas or close the panel to clear the selection. The selection is shared with the Table, and kept in the address (`?select=class:Ticket`), so a reload or a shared link opens with the same selection.

**Search Concepts** stays when you switch views. On the Map it highlights the classes and relations whose name matches, and lists results in the panel: name matches first, then other matches with the reason each was found (for example *Bin: description mentions 'warehouse'; attribute warehouse*). Click a result, or move to it with the arrow keys and press Enter, to select it and centre the Map on it; a relation selects its first arrow. Its details then have a **← Results** link back to the list. In the Table, search filters all three grids, matching any of their text.

**The Table.** The **Table / Map** toggle switches to the **Table**: its Concepts in three grids, **Classes**, **Relations** and **Attributes**, stacked in sections you can collapse. A bar that stays at the top while you scroll counts each grid's rows (*Classes 4 · Relations 1 · Attributes 5*, the attributes a subclass inherits counted under it too); click one to jump to its section. Each section opens with a line on what it means in the Ontology: classes are the kinds of things stored, and an indented class is a subclass that inherits its superclass's attributes and relations; relations say how classes connect, each pattern which class may link to which; attributes are the fields stored on a class or relation.

- **Classes** lists each class in hierarchy order with its superclass, its attribute count (those it inherits in parentheses), its outgoing and incoming relations (`HAS_TRIP → Trip`), its constraints and description.
- **Relations** lists each relation with its patterns, one per line, its attribute count and description.
- **Attributes** lists every attribute with its owner, type, whether it is required or unique, and description; an inherited one is listed under each subclass and marked with the class it comes from (*from Person*). It is grouped by owner, each group headed by the owner, its kind, its superclass and its attribute count; **Group by** switches to grouping by type, or none.

Click a column's name to sort by it, and its filter button to filter it: by text for names and descriptions, by a list of values for types and kinds, or by a switch for required, unique and deprecated. Each grid says how many rows are left (*12 of 34 attributes*), and its column picker shows more columns, such as **Deprecated**, or an attribute's **Owner kind** and **Inherited from**. The sort, filters, grouping and columns are kept in the address, so a reload or a shared link keeps them. Every class and relation name is a link: click it to select that Concept and jump to its row, which is highlighted. An attribute count opens its owner's group of attributes. Each row's **Show on Map** button opens the Map with that Concept selected and centred (an attribute's, its owner). What you select in the Table is highlighted on the Map when you switch, and the other way round.

#### The Changes tab

The tab opens on a **Map** of both versions laid over each other, each class in one place, framed on what changed; the fit view button frames all of it. It works like the [Ontology tab's Map](#the-ontology-tab), with its filters in the same place. Added items are drawn solid, removed ones as dashed ghosts where they used to be, modified ones with a ring, and unchanged ones muted; the key at the bottom left, by the zoom controls, shows these. Each change is coloured by its classification (additive, deprecating or breaking), as in the Diff. A class or relation whose only change is to its description is *documentation-only*, the Diff's cosmetic class, and is marked with a small dot instead. A change to an attribute marks its class or relation as modified, and a class lists just its changed attributes on the Map, diff-style: `− old_name` for a removed one, `+ new_name` for an added one (a rename shows as both), and `~ name` with the change for a modified one, each in its classification's colour. Unchanged attributes stay off the Map. When you select a class, the changed classes and relations outside what it connects to stay readable, with their colour; only unchanged ones fade.

**The change summary.** With nothing selected, the panel on the Map's right is the change summary. It starts with a count per classification (*2 breaking · 3 additive*), each with its colour's swatch, so the counts are also the colour key. Below, the changed classes and relations are grouped by their most severe change, in sections **Breaking**, **Deprecating**, **Additive** and **Documentation-only**, the last one collapsed until you open it. Each entry gives the name on its own line, whether it is a class or relation, then its changes in words (*attribute `wheelchairBoarding` removed*); a change names its classification only when it differs from its section's. A documentation-only entry previews its new description in one line. Point at an entry to bring its class or relation forward on the Map, and click it to select it. A selection's details add its changes from the Diff, and for a documentation-only change, its description **Before** and **After**, removed words struck through and added ones underlined. **← All changes** goes back to the summary, with the entry you came from highlighted. The panel's collapse button shrinks it to a thin rail of the counts; a new selection or search opens it again.

**The Table.** The **Table / Map** toggle switches to the Diff as a grid: the overall classification and a count per level, then a row per change with its Concept, Concept kind, change (added, removed, changed or deprecated), severity and detail, most severe first. It sorts, filters and searches like the Ontology Table, and each row's **Show on Map** shows the class or relation it changed. Documentation-only changes are hidden until you click **Show documentation-only changes**.

#### Promoting a version

**Promote** on a version's page (needs edit access) moves an Alias to that version:

1. Pick an existing Alias, or choose **New Alias** and type a name to create one.
2. Check what changes: the dialog shows the Ontology Diff from the version the Alias points to now, and this version's latest Gate result. Gates never block a Promotion; the result is recorded with it.
3. If you picked the Contract Alias, confirm **Switch Construction Runs and Drift to v*N***: new Construction Runs will declare this version, and Drift will be measured against it.
4. Click **Promote to *alias***.

The Promotion is recorded with you as the actor and shows up under [Promotions](#promotions).

### Construction Runs

The section lists every Construction Run, newest first, with its status, start time, duration, Declared Ontology, Conformance score and the Candidate it produced, if any.

- **Status** filters by All, Running, Finished or Failed, and **Started** by All time or the last 24 hours, 7 days or 30 days.
- **Columns** adds a column per param or metric the runs logged.
- **Table** / **Chart** switches to one chart per run metric, plus Conformance, over the runs' start times. The filters apply to the charts too.

If there are no runs yet, the page shows how to start one from the Python SDK.

**Comparing runs.** Tick two or more runs (the header checkbox selects them all) and click **Compare** to see them side by side: status, start time, Declared Ontology, Candidate and Conformance, then their params, metrics and Evaluator results. Turn on **Show diff only** to hide the rows where every run has the same value.

**A Construction Run's page.** Click a run id to open it. The header shows the full id (with a copy button), its status, when it started and how long it took. If it failed, a banner says why as far as stetiq knows: it observed Concepts its Declared Ontology does not have while the Evolution Mode is *strict*, or it failed before its Graph Source was observed. Three tabs follow:

- **Overview**: its Declared Ontology, Candidate, start and end time and duration; the Observation it ended with (when, which Graph Source, and how many classes, relations and patterns it saw); and its params and metrics.
- **Conformance**: the Conformance score, then the Concepts **Declared but not observed**, those **Observed but not declared**, and any other mismatches (patterns, undeclared value types, required attributes not always set).
- **Evaluations**: every run Evaluator's metrics and, when the Use Case's Competency Questions were executed against the graph, each one's result (*Passed*, *Failed* or *Error*), which check judged it and any error type. Only the verdict is kept, never the rows the query returned.

### Use Case and Competency Questions

The section shows the latest Use Case Version: its description and its Competency Questions, each with its id, question, Cypher query, expected answer and Concept mapping. Below it:

- **Structural answerability**: how many of those Competency Questions the latest Ontology Version can answer, and for each one whether it is *Answerable*, *Unanswerable* (with the Concepts it is missing) or *Unmapped*.
- **Use Case Versions**: every Use Case Version with when it was created and how many Competency Questions it has.

**Editing Competency Questions** (needs edit access). **Add Competency Question** opens a form with an **Id**, a **Question**, and optionally a **Cypher query**, an **Expected answer** (any JSON value the query's rows must match) and a **Concept mapping** (one Concept reference per line, e.g. `Customer`, `Ticket.opened_at` or `(Customer)-[OPENED]->(Ticket)`). Each row also has an edit button, which opens the same form (the id is locked: to change it, remove the question and add a new one), and a remove button.

Every save registers a new Use Case Version, so earlier results stay tied to the version they were judged against. After saving, the page says which Use Case Version you got. If the content is the same as the latest or an earlier version, no new version is created and the page says which one already has it.

**Comparing two Use Case Versions.** Tick two rows in **Use Case Versions** and click **Compare** to see what changed: the description, and the Competency Questions **Added**, **Changed** (field by field, before and after) and **Removed**. Competency Questions are matched by id.

If no Use Case has been registered yet, add a Competency Question here or register one from the [Python SDK](./03-python-sdk.md).

### Observations

The section lists every Observation of the Graph Source, newest first, with its Graph Source scope and the Construction Run it ended, or *None (on demand)* for an Observation taken between runs. Each one is marked **Drift** or **No Drift**.

An Observation with Drift lists what diverged from the Ontology Version of the Contract Alias: the Contract Alias and its version, the Drift thresholds, and each finding with its kind, Concept and detail.

This section is read-only: an Observation needs your graph database credentials, which never leave your own process. Take one with `stetiq observe` (see [CLI](./04-cli.md)) or by ending a Construction Run.

### Promotions

The section is the Promotion audit, newest first: which Alias moved, from which version to which, who moved it, when, and the version's latest Gate result at that moment (*Passed*, *Failed* or *None*). Promote an Ontology Version from [its page](#ontology-versions) to add a row.

## Next steps

- [Python SDK](./03-python-sdk.md) to record Construction Runs and register Use Cases from code.
- [`stetiq.yaml`](./06-stetiq-yaml.md) to define Gates and Drift thresholds in your repository.
