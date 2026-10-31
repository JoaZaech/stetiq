# table/

The Ontology tab's Table view: the Attributes grid and the links between the Table's rows, the selection and the Map.

**Entry points:**

- `AttributesGrid.tsx` (`AttributesGrid`): every attribute of every class and relation, grouped; a `GroupRequest` groups it by owner and scrolls to that owner's group. The grouping lives here too: `ATTRIBUTES_GRID` keeps it in the URL (`attributes.group`: owner, the default, or type), `GROUP_BY` is the "Group by" toggle and `groupHeader` draws a group's header. The grouped rows themselves come from TanStack Table, through `useDataTable` (`@/lib/data-table`) and `useDataTableParams` (`@/lib/data-table-params`).
- `TableLinks.tsx`: `ConceptLink` (a name that selects and scrolls to its row), `AttributeCountLink` (opens the owner's group in the Attributes grid) and `ShowOnMap`.

**Pure modules:**

- `attribute-rows.ts` (`attributeRows`, tested): one row per attribute a class or relation has, its own first, then inherited ones along the superclass chain.
- `table-links.ts`: what the Table's links do (`TableLinks`, `TableLinksContext`, `useTableLinks`), a selected row's highlight (`selectedRowProps`) and the DOM ids rows and groups scroll to (`conceptRowId`, `attributeGroupId`).

The comparison's grid (`OntologyComparisonTable`) lives in `../comparison/` and reuses these links. The selection (`../concept-selection.ts`) and Concepts (`../concepts.ts`) stay in `..`.
