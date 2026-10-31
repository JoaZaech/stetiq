# comparison/

Comparing two Ontology Versions, as a Map or as a Table (`?view=`).

**Entry points:**

- `ChangesTab.tsx` (`ChangesTab`): a version compared with the one before it.
- `OntologyDiffPage.tsx` (`OntologyDiffPage`): the Compare page, any two versions.
- `OntologyComparisonMap.tsx` and `OntologyComparisonTable.tsx`: the two views both of these show, with `MapChangeSummary.tsx` (`MapChangeSummary`, `MapChangesRail`, `LevelCounts`) beside them. `LevelCounts` draws each count with its `SeveritySwatch` (`@/components/SeveritySwatch`), so the headline is the severity key. `DescriptionDiff.tsx` (`DescriptionDiff`): a documentation-only change's description Before and After in a Concept's details, its words marked by `wordDiff` (`@/lib/word-diff`, tested).
- `use-ontology-comparison.ts` (`useOntologyComparison`): the loader, both versions and their Ontology Diff; `comparison-view.ts` (`useComparisonView`): the Table / Map toggle.

**Pure modules:**

- `ontology-map-comparison.ts` (tested): the comparison, what the Map and its change summary read from (base, target, Ontology Diff). It covers two versions superimposed with how each item changed (`compareOntologies`, `changesOf`, `MapChange`), the change summary, a count per level and each changed Concept's changes in words, in a section per level (`summarizeChanges`, `summaryConceptOf`), a documentation-only change's description in both versions and the new one an entry previews (`descriptionChangeOf`, `descriptionPreviewOf`), and what selecting a class or relation selects on the Map (`selectionOf`). The summary and the Map both select through `selectionOf`, so a relation picked in either selects the same link.
- `comparison-rows.ts` (tested): the comparison grid's rows, one per Ontology Diff change (`comparisonRows`).

A change's level is its Diff classification. "More severe" is defined once, by `compareSeverity` in `@/api/ontology-diff` (with `mostSevere` and `MOST_SEVERE_FIRST`), which the comparison, its Table and the plain Ontology Diff view (`@/components/OntologyDiff`) all sort by. Severity's Diff colours are one table, `SEVERITY` in `@/components/severity-style` (with `severityStroke`), which the Map, the change summary and `ClassificationBadge` all draw with.

These modules read what a Diff change concerns from its fields (`owner`, `owner_kind`, `attribute`, `required`, `pattern`) and the cosmetic class, never from its `detail`, which is only shown. `OntologyChange` in `@/api/ontology-diff` is a union by `concept_kind`: an attribute change always states its owner, owner kind and attribute, and an added one whether it is required. `ontology-diff.fixtures.ts` builds the tests' changes from those fields. The UI names the cosmetic class "documentation-only" (`CLASSIFICATION_LABEL` in `@/api/ontology-diff`).

The Map itself is `../map/OntologyMap.tsx`; the selection, version context and `MapView` stay in `..`.
