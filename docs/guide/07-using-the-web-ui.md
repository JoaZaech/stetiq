# Using the web UI

The web UI shows every Knowledge Graph you can read: its Ontology Versions, Construction Runs, Use Case, Observations and Promotions. It is also where you make the governance edits that don't belong in code: promoting an Ontology Version, editing a Knowledge Graph's description and changing its Use Case's Competency Questions, Consumers and Tasks.

Open it with `stetiq ui` (local mode, see [Getting started](./01-getting-started.md#open-the-web-ui)) or at `/ui` on a stetiq server, where you sign in with an API Token (see [Server and API Tokens](./05-server-and-api-tokens.md)). The words used here are explained on the [Concepts](./02-concepts.md) page.

## Finding your way around

The web UI opens on **Home**: your five most recently modified Knowledge Graphs, with **View all** leading to the full list. The line *New to stetiq? Read the guide* under the title opens this guide's first page. The stetiq logo at the top of the sidebar always leads back to Home.

The sidebar looks the same on every page:

- **Home**.
- **The Knowledge Graph switcher**: shows the Knowledge Graph you are in, or *Select a Knowledge Graph*. Click it to see every Knowledge Graph you can read, with a check on the current one; type to search by name, and pick one with the mouse or the arrow keys and Enter. Switching keeps you in the same section: from *support*'s Construction Runs you land on *billing*'s Construction Runs. From a detail or compare page you land on that section's list, since the ids belong to the other Knowledge Graph. **All Knowledge Graphs** at the bottom opens the full list at `/ui/kg`. With the sidebar collapsed to icons, hover the switcher to see the Knowledge Graph's name.
- **The sections**: Overview, Ontology Versions, Construction Runs, Use Case, Observations and Promotions. Inside a Knowledge Graph they lead to its sections. Elsewhere (Home, Settings, Help, the list) they lead into the Knowledge Graph you last opened in this browser. Until you have opened one, or if it no longer exists, they are greyed out with a *Select a Knowledge Graph first* tooltip.
- **Help**: this guide.
- **Settings**: the theme (light, dark or system) and your access. In local mode, Access says every Knowledge Graph is editable and names the user your changes are recorded as. On a server, it shows who you are signed in as, your grants (*read* or *edit* per Knowledge Graph, `*` meaning all of them) and a **Sign out** button.

Breadcrumbs at the top of each page lead back up, e.g. from v3 of *support* to *Ontology Versions*, *support* and *Knowledge Graphs*. Pages, searches, filters, chosen columns and compare views live in the URL, so you can share what you are looking at by copying the address.

## What needs edit access

Some controls change a Knowledge Graph, and they need the *edit* permission on it:

| Action | Where |
| --- | --- |
| **Edit description** | A Knowledge Graph's Overview, and the header of every other section |
| **Promote** | An Ontology Version's page |
| **Add Competency Question** | The Use Case section |
| **Edit** and **Remove** a Competency Question | The header of its sheet: click the question in the Use Case section |
| **Add Consumer** | The Consumers panel of the Use Case section |
| **Edit** and **Remove** a Consumer | The header of its sheet: click its tile in the Use Case section |
| **Add Task** to a Consumer | The Tasks of the Consumer's sheet |
| Edit and remove a Task | Beside the Task in its Consumer's sheet |

Without *edit*, these controls stay visible but disabled, with a *Needs edit access* tooltip. Everything else in the UI is read-only. In local mode every Knowledge Graph is editable. The server checks every change too, so a disabled button is a convenience, not the protection.

## The Knowledge Graphs list

The Knowledge Graphs page (`/ui/kg`) lists every Knowledge Graph you can read, with:

- **Contract Alias version**: the Ontology Version its Contract Alias points to.
- **Latest version**: its newest Ontology Version.
- **Last run**: the status of its newest Construction Run (Running, Finished or Failed), or *No runs*.
- **Last modified**: when it last changed.

Click a column header to sort, and type in **Search by name** to filter. Click a name to open the Knowledge Graph on its [Overview](#overview). If there are none yet, the page shows how to create one from the Python SDK (see [Python SDK](./03-python-sdk.md)).

## Inside a Knowledge Graph

A Knowledge Graph opens on its [Overview](#overview). Every other section starts with the same one-line header: the Knowledge Graph's name, its Contract Alias chip with the version it points to (e.g. `production → v3`) and **Edit description**. The description, the Evolution Mode and the pipeline are on the Overview.

**Edit description** (needs edit access) opens a markdown editor with a **Write** and a **Preview** tab. Saving shows the new description on the Overview to everyone who can read the Knowledge Graph.

### Overview

The Overview is the Knowledge Graph's dashboard. From the top:

- **About**: the first sentence of the description, with the rest behind **More**, the Evolution Mode (*strict* or *evolving*) and **Edit description**.
- **The pipeline** (below): where the Knowledge Graph stands, with its key numbers.
- **Four cards**, each with a link to its whole list:
  - **Recent runs**: the last five runs.
  - **Latest Observations**: the last five, with any Drift.
  - **Current Ontology Version**: the version the Contract Alias points to, its Aliases, and how many Classes, Relations, Attributes and patterns it has.
  - **Recent Promotions**: the last five, with their Gate results.

The pipeline is one row of five numbered stages: upstream pipeline → Gate → Knowledge Graph → Consumer Gate → Consumers. Each stage shows a status with its icon and its numbers (`—` while there is nothing to count), and its name links to its page. Point at the status for its detail, such as when the latest run ended. A grey dashed status means stetiq has nothing to judge yet, never a pass. A stage that isn't green ends with one **next step**: a link to the page where it is fixed, or an action that copies the command that moves it on (point at it to see the command).

| Stage | Numbers | Status | Next step |
| --- | --- | --- | --- |
| **Upstream pipeline** | The latest assessed run's **Conformance**; its status's detail says how long ago the latest run ended | ✓ *Finished*, ✗ *Failed* or *Running*; *No runs* | *Track a run* (`stetiq run`), or *Why run … failed*, opening its Evaluation tab |
| **Gate** | **Gates passed** by the newest Ontology Version, e.g. `2/3`; its status's detail names the version and its latest Gate result | ✓ *Passed* or ✗ *Failed*; *Not gated* | *Evaluate its Gates* (`stetiq gate <name> --version <n>`), or *See the failed Gates* on that version's page |
| **Knowledge Graph** | **Drift findings** of the latest Observation; its status's detail says where the Contract Alias points, e.g. `production → v3`, and when it was observed | ✓ *No Drift* or ⚠ *Drift*; *Not observed* | *Take an Observation* (`stetiq observe <name>`), or *Review n Drift findings*, opening that Observation |
| **Consumer Gate** | **Consumer Gates passed** in each Consumer's latest verdict, e.g. `1/2` | ✗ *Failed* if any failed, ✓ *Passed* if all passed; *Not evaluated yet* while one has no verdict, *None declared* when no Consumer declares one | *Declare one on a Consumer* or *See the failing Consumers* (the Use Case's Consumers tab), or *Evaluate them* (`stetiq consumer gate <name>`) |
| **Consumers** | Consumers the latest Ontology Version is **ready** for, e.g. `2/3` (a Consumer without Tasks isn't counted), and the Competency Questions it answers (**CQs answerable**) | ✓ *Ready* if all are, ✗ *Not ready* otherwise; *Not checked yet*, *No Tasks* or *No Consumers* | *n questions unanswerable*, or *n questions can't be checked*, opening the question catalog filtered to them |

The Consumers and the Consumer Gate are those of the latest Use Case Version. The Consumer Gate is checked by `stetiq consumer gate` in your pipeline's CI.

### Ontology Versions

The section lists every Ontology Version, newest first, with its origin, when it was created and the Aliases pointing to it. The Contract Alias's chip is highlighted with a star, and an Ontology Version no Alias has pointed to yet is marked **Candidate**.

- **Search versions** filters by number (`v3`), origin or Alias.
- **Columns** adds a column per Evaluator metric.
- **Table** / **Chart** switches to one chart per Evaluator metric across versions, with a search box to find a metric.

**Comparing two versions.** Tick two rows and click **Compare** to see the Ontology Diff from the older to the newer version. Any two versions can be compared, not only neighbours. The Compare page works like the [Changes tab](#the-changes-tab): it opens on a **Map** of both versions laid over each other, the **Table / Map** toggle switches to the Diff as a grid, and **Consumer impact** above the changes shows whom they hit.

**An Ontology Version's page.** Click a version number to open it. It shows the version's Aliases and three tabs:

- **Overview**: first four tiles, the same on every evaluated page: **Conformance** (of the Construction Run that produced the version), **CQ coverage** (Competency Questions it can answer, of the latest Use Case Version), **Gates** (passed of evaluated) and **Drift**, which shows *—* because Drift belongs to Observations. Then its latest **Gate result**, as a status with *n of m Gates failed* or *All m Gates passed* and when it was evaluated. Each failed Gate is listed with its reasons; the passed ones fold under ***k* passed**. A version no Gate was evaluated on shows *Not gated*. Then its **Evaluator results**, one card per Evaluator: a readable title (e.g. *Concepts with a Definition*) over the Evaluator's own name, one or two headline metrics, ratios as percentages and counts as *a / b* where there is a total, and an ⓘ that explains it. Your own Evaluators get a card under their name with their first metric. **Show all metrics** opens the full table (Evaluator, metric, value and the Use Case Version it was judged against): the names there are the ones Gates use. **Details**, folded at the bottom, holds its number, origin, content hash (with a copy button), when it was created and, for a version produced by a Construction Run, a link to that run.
- **Ontology**: the version's Concepts, on a Map or in a Table. See [The Ontology tab](#the-ontology-tab).
- **Changes**: the Ontology Diff from the previous version. v1 has nothing to compare with. See [The Changes tab](#the-changes-tab).

#### The Ontology tab

The tab opens on a **Map**: each class is a box, wide enough for its whole name, and each pattern an arrow from one class to another, labelled with its relation. Two relations between the same classes are two separate arrows, and a relation from a class to itself is a loop. Drag to pan, and scroll or use the **+**/**−** buttons to zoom. The Map never opens smaller than its relation names can be read: a larger Ontology opens part in view, for you to pan. The fit view button frames the whole Map, zooming out as far as it takes. Zoomed out further, relation names are hidden, except on what you have selected and, when comparing, on the arrows that changed; zoom back in to see them all. **Hide deprecated** and **Hide subclass links**, in the header row beside the **Table / Map** toggle, take those off the Map.

**Selecting.** Click a class to highlight what it connects to and open its details in the panel on the Map's right: description, superclass, attributes (those it inherits are marked with the class they come from) and constraints. Click an arrow for its relation's description and attributes. With a class selected, shift-click another to highlight every shortest path between them, relations taken either way round and including those a class inherits from its superclass; the panel then shows the **Shortest path**, listing each path, or says that no path connects them. Press Escape, click the empty canvas or close the panel to clear the selection. The selection is shared with the Table, and kept in the address (`?select=class:Ticket`), so a reload or a shared link opens with the same selection.

**Search Concepts** stays when you switch views. On the Map it highlights the classes and relations whose name matches, and lists results in the panel: name matches first, then other matches with the reason each was found (for example *Bin: description mentions 'warehouse'; attribute warehouse*). Click a result, or move to it with the arrow keys and press Enter, to select it and centre the Map on it; a relation selects its first arrow. Its details then have a **← Results** link back to the list. In the Table, search filters all three grids, matching any of their text.

**The Table.** The **Table / Map** toggle switches to the **Table**: its Concepts in three grids, **Classes**, **Relations** and **Attributes**, stacked in sections you can collapse. A bar that stays at the top while you scroll counts each grid's rows (*Classes 4 · Relations 1 · Attributes 5*, the attributes a subclass inherits counted under it too); click one to jump to its section. Each section opens with a line on what it means in the Ontology: classes are the kinds of things stored, and an indented class is a subclass that inherits its superclass's attributes and relations; relations say how classes connect, each pattern which class may link to which; attributes are the fields stored on a class or relation.

- **Classes** lists each class in hierarchy order with its superclass, its attribute count (those it inherits in parentheses), its outgoing and incoming relations (`HAS_TRIP → Trip`), its constraints and description.
- **Relations** lists each relation with its patterns, one per line, its attribute count and description.
- **Attributes** lists every attribute with its owner, type, whether it is required or unique, and description; an inherited one is listed under each subclass and marked with the class it comes from (*from Person*). It is grouped by owner, each group headed by the owner, its kind (*Class* or *Relation*), its superclass and its attribute count; **Group by** switches to grouping by type, or none.

Click a column's name to sort by it, and its filter button to filter it: by text for names and descriptions, by a list of values for types and kinds, or by a switch for required, unique and deprecated. Each grid says how many rows are left (*12 of 34 attributes*), and its column picker shows more columns, such as **Deprecated**, or an attribute's **Owner kind** and **Inherited from**. The sort, filters, grouping and columns are kept in the address, so a reload or a shared link keeps them. Every class and relation name is a link: click it to select that Concept and jump to its row, which is highlighted. An attribute count opens its owner's group of attributes. Each row's **Show on Map** button opens the Map with that Concept selected and centred (an attribute's, its owner). What you select in the Table is highlighted on the Map when you switch, and the other way round.

#### The Changes tab

The tab opens on a **Map** of both versions laid over each other, each class in one place, framed on what changed; the fit view button frames all of it. It works like the [Ontology tab's Map](#the-ontology-tab), with its filters in the same place. Added items are drawn solid, removed ones as dashed ghosts where they used to be, modified ones with a ring, and unchanged ones muted; the key at the bottom left, by the zoom controls, shows these. Each change is coloured by its classification (additive, deprecating or breaking), as in the Diff. A class or relation whose only change is to its Definition or Alternative Labels is *documentation-only*, the Diff's cosmetic class, and is marked with a small dot instead. A change to an attribute marks its class or relation as modified, and a class lists just its changed attributes on the Map, diff-style: `− old_name` for a removed one, `+ new_name` for an added one (a rename shows as both), and `~ name` with the change for a modified one, each in its classification's colour. Unchanged attributes stay off the Map. When you select a class, the changed classes and relations outside what it connects to stay readable, with their colour; only unchanged ones fade.

**The change summary.** With nothing selected, the panel on the Map's right is the change summary. It starts with a count per classification (*2 breaking · 3 additive*), each with its colour's swatch, so the counts are also the colour key. Below, the changed classes and relations are grouped by their most severe change, in sections **Breaking**, **Deprecating**, **Additive** and **Documentation-only**, the last one collapsed until you open it. Each entry gives the name on its own line, whether it is a class or relation, then its changes in words (*attribute `wheelchairBoarding` removed*); a change names its classification only when it differs from its section's. A documentation-only entry previews its new Definition in one line. Point at an entry to bring its class or relation forward on the Map, and click it to select it. A selection's details add its changes from the Diff, and for a documentation-only change, its Definition **Before** and **After**, removed words struck through and added ones underlined. **← All changes** goes back to the summary, with the entry you came from highlighted. The panel's collapse button shrinks it to a thin rail of the counts; a new selection or search opens it again.

**The Table.** The **Table / Map** toggle switches to the Diff as a grid: the overall classification and a count per level, then a row per change with its Concept, Concept kind (*Class*, *Relation*, *Attribute* or *Vocabulary*), change (added, removed, changed or deprecated), severity and detail, most severe first. It sorts, filters and searches like the Ontology Table, and each row's **Show on Map** shows the class or relation it changed. Documentation-only changes are hidden until you click **Show documentation-only changes**.

**Consumer impact.** Above the changes, **Consumer impact** lists one item per Task of the latest Use Case Version the changes hit. Each item shows an icon for how it is hit: red when it is *affected* (a breaking change to a Concept one of its Competency Questions needs), amber when it *will be affected* (a deprecating one), and a grey dashed circle when its impact is *unknown* (a question with neither a Concept mapping nor a query). Next to it are the Task, its Consumer's name, and one line on why, such as "breaks Ticket.opened_at", "deprecates Agent" or "can't tell: no Concept mapping or query". Click an item to see the questions it hits, each followed by the Concepts whose changes hit it, in their classification's colour. Items are listed the most severe first, then by Consumer and Task. Hit questions no Task needs come last, titled by the question, with a **No Consumer** chip. A Consumer the changes don't touch is left out, and when nothing is hit the section says **No Consumer is affected**. Without a Use Case the section says there is none, so no Consumers are declared. See [Consumer impact](./03-python-sdk.md#consumer-impact) for how changes are followed to Consumers.

#### Promoting a version

**Promote** on a version's page (needs edit access) moves an Alias to that version:

1. Pick an existing Alias, or choose **New Alias** and type a name to create one.
2. Check what changes: the dialog shows the Ontology Diff from the version the Alias points to now, its **Consumer impact** (an item per Task it affects or will affect, as on the Changes tab), and this version's latest Gate result. With no impact it says **No Consumer is affected**; without a Use Case it says no Consumers are declared. Neither the impact nor the Gates block a Promotion: they show who downstream has to change, and the Gate result is recorded with it.
3. If you picked the Contract Alias, confirm **Switch Construction Runs and Drift to v*N***: new Construction Runs will declare this version, and Drift will be measured against it.
4. Click **Promote to *alias***.

The Promotion is recorded with you as the actor and shows up under [Promotions](#promotions).

### Construction Runs

The section lists every Construction Run, newest first, in a table: its short id, then a column for each of the params `extractor`, `model` and `sources` that any run logged (**Sources** shows a count, *5 sources*; point at it to list them), then its status, start time, duration, Declared Ontology, Conformance, its Gate verdict and the Candidate it produced, if any. A line under the table counts the runs shown.

- **Conformance** is a percentage, coloured by how close it is to 100 %: green from 95 %, amber from 80 %, red below.
- **Gate** shows the run's latest recorded Gate result as **Passed** (green check) or **Failed** (red cross). A run CI never gated shows **Preview** (grey dashed circle) when it has a Gate Preview, whatever the preview judges: pointing at it says whether it passes or fails against current Gates, and that it is not recorded. Only a Gate result CI records counts. A Knowledge Graph that was never gated shows *—*.

- **Search runs** matches a run's id, its param values and its versions (*v2*).
- **Status** filters by All, Running, Finished or Failed, and **Started** by All time or the last 24 hours, 7 days or 30 days. The search and filters are part of the URL.
- **Columns** adds a column per other param, or per metric, the runs logged.
- **Table** / **Chart** switches to charts over the runs' start times: one per run metric, one for Conformance, and one per Evaluator result metric (each Evaluator `parameters` configuration charted on its own, e.g. `review (min_confidence=0.5)/score`). **Search metric charts** narrows them by name, and the filters apply to the charts too. A chart for a KPI a Gate covers draws each of the Gate's bounds as a dashed line (labelled, e.g. *min 0.8*, and listed under **Bounds**) and marks each run's point *pass* (a circle) or *fail* (a diamond), judged as on the compare page: a recorded Gate result about the run wins over its Gate Preview, and a note under the title says where the verdicts came from (*Verdicts: 1 recorded, 3 preview*). The bound lines are those of the current Gates, the ones the Gate Previews use, so a run's *recorded* verdict can come from an older bound than the line shows: a point can pass below the line, or fail above it. Charts of the run metrics your pipeline logs are never judged, even one named like a gated KPI. Click a point to open the KPI drill-down for that run (see below).

If there are no runs yet, the page shows how to start one from the Python SDK.

**Comparing runs.** Tick two or more runs (the header checkbox selects them all) and click **Compare** to see them side by side: status, start time, Declared Ontology, Candidate and Conformance, then their params, metrics and Evaluator results. Turn on **Show diff only** to hide the rows where every run has the same value.

If the Knowledge Graph has been gated, each KPI a Gate covers (Conformance, or the Evaluator result metric a `metric` Gate names, with its `parameters`) shows *pass* or *fail* next to each run's value, and its row says what share of the compared runs pass, with a pass/fail bar. A run with no value for a gated KPI shows *no result* rather than *fail*, though its overall verdict still counts it as failed. Each verdict is marked *recorded*, when it comes from a Gate result CI recorded about that run, or *preview*: judged against current Gates, the Gates of the latest Gate result about a run, re-evaluated on the spot and never recorded (a Gate Preview). A note at the top names that Gate result. A recorded Gate result always wins over a preview. The **Gates** section lists every Gate, including Ontology Diff and count drop Gates, with each run's pass or fail, and **All Gates passed** per run. The metrics your pipeline logs are never gated. A Knowledge Graph that was never gated shows every value without a verdict: write Gates in [`stetiq.yaml`](./06-stetiq-yaml.md) and run `stetiq gate` to turn verdicts on.

**The KPI drill-down.** Click a KPI cell on the compare page, or a point on a run chart, to open a side sheet about that run's KPI: its value (or *no result*), its verdict marked *recorded* or *preview* with each covering Gate's pass or fail and reasons, and, for an Evaluator result metric, the Evaluator's detail items about that metric. A KPI no Gate covers says so. A link at the bottom opens the run page tab the KPI comes from: **Evaluation**, or the **Overview** for a run metric.

**A Construction Run's page.** Click a run id to open it. The title is the run's short id; under it are its status, when it started and how long it took. If it failed, a one-line banner says why as far as stetiq knows: *Failed: 4 Concepts observed but not declared (strict mode).*, with **Show** to open those findings, or *Failed before the Graph Source was observed.* Then come four KPI tiles, the same on every evaluated page: **Conformance** (the run's score), **CQ coverage** (Competency Questions executed that passed, of all executed), **Gates** (Gates passed in the run's recorded Gate result) and **Drift** (findings of the Observation the run ended with). A tile that doesn't apply shows *—*. Two tabs follow:

- **Overview**: its **Details**: the full run id (with a copy button), Declared Ontology, Candidate, start and end time and duration; the Observation it ended with (when, which Graph Source, and how many classes, relations and patterns it saw); and its params and metrics.
- **Evaluation**: **Findings**, the Conformance mismatches in one table (Concept, Kind, Finding, Change) that you can search and filter by **Finding** and **Kind**. A finding is *Declared but not observed*, *Observed but not declared*, *Undeclared value type*, *Required but not always set*, *Outside the cardinality* (a pattern whose observed out- or in-degree falls outside its declared bounds), *Value outside the Vocabulary* (with the value and how many times it was observed) or *Deprecated value* (reported, but it conforms and does not lower the score). For a run that gave rise to a Candidate, a line says it was **judged against** that Candidate, with a link to it: what the run added is the Candidate's Ontology Diff, so it isn't listed as observed but not declared; the Candidate's *Unjustified additions* card judges those additions. Then **Evaluator results**, one card per run Evaluator (e.g. *Questions executed* with *Passed 1 / 2*), with **Show all metrics** for the full table. When the Use Case's Competency Questions were executed against the graph, **Competency Questions** lists each with its result: **Passed**, **Failed** or **Error**. Click a question to open its side sheet, with an **In this run** part: the result, which check judged it (*non-empty result* or *expected answer*) and any error type. Only the verdict is kept, never the rows the query returned. Links to the old **Conformance** and **Evaluations** tabs open this tab.

### Use Case and Competency Questions

One line names the latest Use Case Version, when it was created and its description. Below it are three tabs, kept in the URL: **Questions**, **Consumers** and **Versions**.

**Questions** is a catalog of the latest Use Case Version's **Competency Questions**. KPI tiles at the top show:

- **CQ coverage**: how many the latest Ontology Version answers, such as 2/9.
- **Unanswerable**
- **Can't check**
- **Not used by any Task**

Under the tiles is a toolbar:

- a search box, which matches the question text and its id
- a **Status** filter, with a count per status
- a **Task** filter: one Task, or *No Task* for the questions no Consumer's Task needs (in a Use Case without Consumers, that is every question)
- **Add Competency Question** on the right

The table has a **Question**, **Tasks** and **Status** column. Click a column header to sort by it; sorting by Status puts the worst first. Long catalogs show 50 rows per page. The search, the filters, the sort and the page are all kept in the URL. A question's status is its status on the latest Ontology Version:

- **Answerable** (green check): the Ontology Version has every Concept the question needs.
- **Unanswerable** (red cross): Concepts it needs are missing.
- **Can't check** (grey dashed circle): the question has neither a Concept mapping nor a query, so stetiq can't tell. Point at it for that explanation.

The status comes from the stored structural answerability result. Until the latest Ontology Version has been judged against this Use Case Version, the tiles show "—" and the rows show no status.

Click a question to open its **side sheet**, which shows the question and its status, then the **Missing Concepts** of an unanswerable question, **Needed by** (each Consumer · Task that needs it, or *Not used by any Task*) and **Author details**: its id, Cypher query, expected answer and Concept mapping. **Edit** and **Remove** sit in the sheet's header. The open sheet is part of the URL, so you can link to a question, a reload keeps it open, and the browser's Back closes it.

The other two tabs:

- **Consumers**: a tile per Consumer the Use Case declares, with an icon for its kind (an application, an agent, a dashboard and a team each have their own; any other kind gets a generic one), its name and the first line of its description. Each tile has one **readiness** line: "*n* of *m* Tasks ready", green when all are and red otherwise. A Task is ready when the latest Ontology Version answers every Competency Question it needs. Readiness is always shown for the latest Ontology Version: the page has no version selector. It reads **Not checked yet** (grey) until that Ontology Version has been judged against this Use Case Version, or when the Knowledge Graph has no Ontology Version, and **No Tasks** (grey) for a Consumer that declares none. A Consumer that declares a Consumer Gate also has a **Consumer Gate** line with its latest verdict: *Consumer Gate passed*, *Consumer Gate failed* or *Consumer Gate not evaluated yet*; a Consumer without one has no such line. You can edit Consumers and Tasks here (see below) or declare them in the Use Case you register from the [Python SDK](./03-python-sdk.md#use-cases-and-competency-questions) or the [CLI](./04-cli.md#use-cases).

  Click a tile to open the Consumer's **side sheet**. It shows the Consumer's kind, name, id, contact and description, with **Edit** and **Remove** in its header, then:

  - **Tasks**: each Task's description and id, with an icon for whether it is ready. Point at a red icon to see why, such as "Not ready: 1 unanswerable, 1 can't check". Click a Task to expand it to the Competency Questions it needs, each with its status (or *Needs no Competency Question*). Click a question to show its sheet in place of the Consumer's, with **Back** to return; only one sheet is open at a time.
  - **Consumer Gate**: the Consumer Gates the Consumer declares in this Use Case Version (name, check, Task and its limit, such as "at most −10% rows") and its latest verdict from `stetiq consumer gate`: **Passed** or **Failed**, the Ontology Version and run it judged, and how long ago. A failed verdict lists each failing Task / Competency Question with its row change, such as "5 → 2 rows (−60.0%, limit −10%)", or says what could not be compared (no baseline run, or no row count on a run). A question declared since the baseline run is listed as *new since the baseline run, not compared*; it fails nothing. **Not evaluated yet** means the Consumer declares Consumer Gates but has no verdict; **No Consumer Gate declared** means it declares none. Consumer Gates are declared in `use-case.yaml` (see [Consumer Gates](./03-python-sdk.md#consumer-gates)); the web UI shows them but does not edit them, and editing a Consumer here keeps them.

  Like a question's, the Consumer's sheet is part of the URL: you can link to it, a reload keeps it open, and the browser's Back steps back through the sheets you opened.

- **Versions**: every Use Case Version with when it was created and how many Competency Questions it has.

**Editing Competency Questions** (needs edit access). **Add Competency Question** opens a form with an **Id**, a **Question**, and optionally a **Cypher query**, an **Expected answer** (any JSON value the query's rows must match) and a **Concept mapping** (one Concept reference per line, e.g. `Customer`, `Ticket.opened_at` or `(Customer)-[OPENED]->(Ticket)`). In a question's sheet, **Edit** opens the same form (the id is locked: to change it, remove the question and add a new one) and **Remove** removes it, closing the sheet. Removing a question that Tasks need names those Tasks first: they stay, without that question. A new question's id must differ from every other Competency Question, Consumer and Task id in the Use Case.

**Editing Consumers and Tasks** (needs edit access). **Add Consumer** opens a form with an **Id** and a **Name**, and optionally a **Kind** (an application, an agent, a dashboard, a team...), a **Contact** and a **Description**. In a Consumer's sheet, **Edit** opens the same form (the id is locked), **Remove** removes the Consumer with all its Tasks after naming them (the Competency Questions stay) and closes the sheet, and **Add Task** adds a Task: an **Id**, a **Description**, and the Competency Questions it needs, ticked from the Use Case's. Each Task in the sheet has its own edit and remove buttons. A new Consumer's or Task's id must differ from every other Consumer, Task and Competency Question id in the Use Case.

Every save registers a new Use Case Version, so earlier results stay tied to the version they were judged against. After saving, the page says which Use Case Version you got. If the content is the same as the latest or an earlier version, no new version is created and the page says which one already has it.

**Comparing two Use Case Versions.** Tick two rows on the **Versions** tab and click **Compare** to see what changed: the description, and the Competency Questions **Added**, **Changed** (field by field, before and after) and **Removed**. Competency Questions are matched by id.

If no Use Case has been registered yet, add a Competency Question here or register one from the [Python SDK](./03-python-sdk.md).

### Observations

The section opens with the **Alignment trend**: one line of Conformance scores over time, for every Construction Run (filled points, *run*) and every on-demand Observation (hollow points, *on demand*). It answers whether the graph is getting more or less aligned with its Ontology. Hover a point for its score, its source and the Ontology Version it was judged against: a run's own version (or its Candidate), or for an on-demand Observation the Contract Alias's version at that moment. Click a point to open its Observation. The line has no threshold and raises no Drift.

Under it is a table of every Observation of the Graph Source, newest first: when it was taken, **No Drift** or **Drift**, its source (*run* with the short id of the Construction Run it ended, or *on demand*), the Ontology Version it was checked against, its **Conformance** (*no score* for an Observation taken before stetiq scored them), and how many findings it had. **Search Observations** matches a run id, a version (`v3`) or the Contract Alias; **Status** keeps only Drift or No Drift.

Click a row to open it in a side panel. Its top line holds the Contract Alias, the version, the Drift thresholds (*max drop*, *max rise*, *max violation rise* in percentage points) and the *baseline*: the time of the Baseline Observation its Violation Rates were compared with, or *itself* for the first Observation since the contract changed. Then the four evaluation tiles, of which **Conformance** (the point's score on the alignment trend, `—` without one) and **Drift** apply here, and the findings table: **Concept**, its **Kind** (**Class**, **Relation**, **Attribute** or **Pattern**), the **Finding** (e.g. *Observed but not declared*, *Count rose*, *Violation Rate rose*) and the **Change**, such as `1 → 4 (+300%)`. Filter it by finding or kind, or search it. An *undeclared value* finding is a value of a Vocabulary-bound Attribute that the Contract Alias's Vocabulary does not have: its Concept is the Attribute (`Owner.attribute`), and its change names the value, how many hold it and their share, such as `“on_hold” × 2 (25%)`. A *Violation Rate rose* finding names the check and the rate in the baseline and now, such as `Required but not always set: 0.5% → 3% (+2.5 pts)`; on a Pattern it names the degree, such as `Outside the cardinality (out-degree): 0% → 5% (+5 pts)`. Below the findings, **Not comparable** lists the checks that lacked their input and so raised no Drift, each with its reason.

This section is read-only: an Observation needs your graph database credentials, which never leave your own process. Take one with `stetiq observe` (see [CLI](./04-cli.md)) or by ending a Construction Run.

### Promotions

The section is the Promotion audit, newest first: which Alias moved, from which version to which, who moved it, when, and the version's latest Gate result at that moment, as a status: ✓ *Passed*, ✗ *Failed* or a grey *Not gated*. Promote an Ontology Version from [its page](#ontology-versions) to add a row. **Search Promotions** matches an Alias, a version or an actor; **Gate** keeps only one Gate result.

## Next steps

- [Python SDK](./03-python-sdk.md) to record Construction Runs and register Use Cases from code.
- [`stetiq.yaml`](./06-stetiq-yaml.md) to define Gates and Drift thresholds in your repository.
