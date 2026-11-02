# UI personas

The people the web UI is built for. A change to a page starts from the persona who lands on it and the first question they bring. These are roles, not GLOSSARY terms: a **Consumer** is a downstream system, and one persona below builds one.

Assume production scale on every page: hundreds of Competency Questions, thousands of Construction Runs, dozens of Ontology Versions.

## Pipeline engineer

Owns the upstream pipeline that builds the Knowledge Graph (extractor, model, sources) and tracks its Construction Runs from CI or a notebook.

- **First question:** did my last run pass, and if not, why?
- **Then:** what changed from the run before? Which params (extractor, model, sources) gave the best Conformance?
- **Lands on:** Construction Runs, a run's Evaluation tab, Compare.
- **Needs in five seconds:** the run's status, Conformance, Gates and the first failing finding.
- **Frustrated by:** explanations sitting between them and the findings, and run params shown as chips they can't sort by.

## Ontology owner

Curates the Ontology: reviews Candidates, promotes Ontology Versions to the Contract Alias, and watches Drift in the live graph.

- **First question:** is the graph healthy right now?
- **Then:** what is drifting? What would promoting this Candidate change, and does it pass its Gates?
- **Lands on:** Overview, Ontology Versions (Map, Changes), Observations, Promotions.
- **Needs in five seconds:** the dashboard's KPI tiles and which alias points at which version.
- **Frustrated by:** an empty Overview, and the same evaluation laid out differently on each page.

## Use case owner

The domain lead whose questions the graph exists to answer (e.g. a maintenance lead). They write Competency Questions and Tasks and think in questions, not schemas.

- **First question:** how many of my questions can the graph answer?
- **Then:** which ones can't it answer, and which Task needs them?
- **Lands on:** Use Case › Questions, Overview's CQ coverage tile.
- **Needs in five seconds:** coverage as one number, then a list they can search and filter to the unanswerable ones.
- **Frustrated by:** a list that only scrolls, ontology identifiers without plain words, and walls of text.

## Consumer developer

Builds a downstream application (a Consumer) that queries the graph, and decides when it takes a new Ontology Version.

- **First question:** is my Consumer ready for the version that's coming?
- **Then:** which of my Tasks does this change break, and does my Consumer Gate pass?
- **Lands on:** Use Case › Consumers, a version's Consumer impact, Overview's Consumers tile.
- **Needs in five seconds:** ready or not ready, and the one reason why.
- **Frustrated by:** having to read the Ontology Diff to learn whether it affects them.

## Rules these personas imply

- **Same frame everywhere.** Every list page is a toolbar (search, filters, actions) over a table, with the count below. Every detail page is the ID and status, one metadata line, the KPI tiles, then tabs. A persona who has learnt one page has learnt them all.
- **Same four tiles for every evaluation.** Conformance · CQ coverage · Gates · Drift, in that order. A tile that doesn't apply shows "—".
- **Numbers before words.** The page shows the value. The explanation sits in an ⓘ tooltip (two sentences at most) that links to the guide.
- **Scale by default.** Any list that can grow gets search, filters and paging the day it ships.
- **Shipped only.** The UI shows what works today.

## Using this file

Before a UI change, name the persona or personas it serves and their first question on that page. Then check the change answers that question first. To review a change as these personas, run the `ui-persona-review` agent (`.claude/agents/ui-persona-review.md`). Add a persona here when a new kind of user shows up in issues or feedback.
