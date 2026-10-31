# comparison/

Comparing two Ontology Versions, as a Map or as a Table (`?view=`).

**Entry points:**

- `ChangesTab.tsx` (`ChangesTab`): a version compared with the one before it.
- `OntologyDiffPage.tsx` (`OntologyDiffPage`): the Compare page, any two versions.
- `OntologyComparisonMap.tsx` and `OntologyComparisonTable.tsx`: the two views both of these show, with `MapChangeSummary.tsx` (`MapChangeSummary`, `LevelCounts`, `ChangeLevelBadge`) beside them.
- `use-ontology-comparison.ts` (`useOntologyComparison`): the loader, both versions and their Ontology Diff; `comparison-view.ts` (`useComparisonView`): the Table / Map toggle.

**Pure modules:**

- `ontology-map-comparison.ts` (tested): the comparison model, two versions superimposed with how each item changed (`compareOntologies`, `changesOf`, `MapChange`).
- `ontology-map-summary.ts` (tested): the change summary, counts per level and each changed Concept's changes in words (`summarizeChanges`, `levelOf`).
- `comparison-rows.ts` (tested): the comparison grid's rows, one per Ontology Diff change (`comparisonRows`).
- `severity-style.ts`: severity's Diff colours (`SEVERITY`, `severityStroke`).

The Map itself is `../map/OntologyMap.tsx`; the selection, version context and `MapView` stay in `..`.
