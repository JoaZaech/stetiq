import { useMemo } from 'react'
import { useSearchParams } from 'react-router'
import { CLASSIFICATION_LABEL, compareSeverity, isCosmetic } from '@/api/ontology-diff'
import { ClassificationBadge } from '@/components/OntologyDiff'
import { DataTable, DataTableRowCount } from '@/components/DataTable'
import { ErrorAlert } from '@/components/ErrorAlert'
import { SearchInput } from '@/components/SearchInput'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { createDataTableColumnHelper, filterColumn, useDataTable } from '@/lib/data-table'
import { type DataTableParamsOptions, useDataTableParams } from '@/lib/data-table-params'
import { formatCount } from '@/lib/format'
import { setOrDeleteParam } from '@/lib/search-params'
import { type ComparisonRow, comparisonRows } from './comparison-rows'
import { isSelectedRow, selectedRows, useConceptSelection, useShowOnMap } from '../concept-selection'
import { LevelCounts } from './MapChangeSummary'
import { type OntologyComparison, summarizeChanges } from './ontology-map-comparison'
import { selectedRowProps, type TableLinks, TableLinksContext } from '../table/table-links'
import { ShowOnMap } from '../table/TableLinks'
import { useOntologyComparison } from './use-ontology-comparison'

/** Shows the cosmetic (documentation-only) changes, which the grid leaves out by default. */
const COSMETIC_PARAM = 'changes.docs'

const column = createDataTableColumnHelper<ComparisonRow>()

const columns = column.columns([
  column.accessor('concept', {
    header: 'Concept',
    ...filterColumn('text'),
    cell: ({ getValue }) => <span className="font-mono text-xs">{getValue()}</span>,
  }),
  column.accessor('conceptKind', { header: 'Concept kind', ...filterColumn('values') }),
  column.accessor('change', { header: 'Change', ...filterColumn('values') }),
  // Filtered and searched by the UI's name for the level (cosmetic is "documentation-only").
  column.accessor((r) => CLASSIFICATION_LABEL[r.level], {
    id: 'level',
    header: 'Severity',
    ...filterColumn('values'),
    // The weightiest first when sorted descending, as the rows come.
    sortFn: (a, b) => compareSeverity(a.original.level, b.original.level),
    sortDescFirst: true,
    cell: ({ row }) => <ClassificationBadge classification={row.original.level} />,
  }),
  column.accessor('detail', { header: 'Detail', ...filterColumn('text'), enableSorting: false }),
  column.display({
    id: 'map',
    header: '',
    cell: ({ row }) => <ShowOnMap concept={row.original.owner} />,
  }),
])

/** The grid's URL state, beside the page's own params (e.g. the Compare page's `?id=`). */
const CHANGES_GRID: DataTableParamsOptions = {
  key: 'changes',
  filters: { concept: 'text', conceptKind: 'values', change: 'values', level: 'values', detail: 'text' },
}

/**
 * Loads and shows the comparison from version `base` to `target` as a grid of its
 * Ontology Diff's changes: the Table view of the Changes tab and the Compare page.
 */
export function OntologyComparisonTable({
  knowledgeGraph,
  base,
  target,
}: {
  knowledgeGraph: string
  base: number
  target: number
}) {
  const { comparison, error } = useOntologyComparison(knowledgeGraph, base, target)
  if (error) return <ErrorAlert error={error} />
  if (!comparison) return <Skeleton className="h-32 w-full" />
  return <ComparisonGrid comparison={comparison} base={base} target={target} />
}

/**
 * The overall classification and a count per level, then one row per change: Concept,
 * Concept kind, Change, Severity and Detail, each row with its "Show on Map".
 * Documentation-only changes are left out, and counted, until shown. A region named
 * "Ontology Diff".
 */
function ComparisonGrid({ comparison, base, target }: { comparison: OntologyComparison; base: number; target: number }) {
  const { diff } = comparison
  const all = useMemo(() => comparisonRows(comparison), [comparison])
  const counts = useMemo(() => summarizeChanges(comparison).counts, [comparison])
  const [params, setParams] = useSearchParams()
  const showCosmetic = params.get(COSMETIC_PARAM) === '1'
  const cosmeticCount = all.filter((r) => isCosmetic(r.level)).length
  const rows = useMemo(
    () => (showCosmetic ? all : all.filter((r) => !isCosmetic(r.level))),
    [all, showCosmetic],
  )
  const grid = useDataTableParams(CHANGES_GRID)
  const table = useDataTable({
    data: rows,
    columns,
    getRowId: (row) => row.id,
    globalFilterFn: 'includesString',
    ...grid.tableOptions,
  })
  const [selection, setSelection] = useConceptSelection()
  const highlighted = useMemo(() => selectedRows(comparison.ontology, selection), [comparison, selection])
  const showOnMap = useShowOnMap()
  const links = useMemo(
    (): TableLinks => ({
      select: setSelection,
      showOnMap,
    }),
    [setSelection, showOnMap],
  )
  const setShowCosmetic = (show: boolean) =>
    setParams((p) => setOrDeleteParam(p, COSMETIC_PARAM, show ? '1' : null), { replace: true })

  return (
    <section aria-label="Ontology Diff" className="space-y-4">
      {diff.classification === null ? (
        <p className="text-sm text-muted-foreground">
          No changes between v{base} and v{target}.
        </p>
      ) : (
        <TableLinksContext value={links}>
          <div className="flex flex-wrap items-center gap-x-4 gap-y-2 text-sm">
            <p className="font-medium">
              Overall: <ClassificationBadge classification={diff.classification} />
            </p>
            <LevelCounts counts={counts} />
          </div>
          <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2">
            <SearchInput
              label="Search changes"
              className="w-full max-w-sm"
              value={table.store.state.globalFilter ?? ''}
              onChange={table.setGlobalFilter}
            />
            <div className="flex items-center gap-3">
              {cosmeticCount > 0 && (
                <p className="text-xs text-muted-foreground">
                  {!showCosmetic && `${formatCount(cosmeticCount, 'documentation-only change')} hidden`}
                  <Button
                    variant="link"
                    size="sm"
                    className="h-auto px-1.5 text-xs"
                    onClick={() => setShowCosmetic(!showCosmetic)}
                  >
                    {showCosmetic ? 'Hide documentation-only changes' : 'Show documentation-only changes'}
                  </Button>
                </p>
              )}
              <DataTableRowCount table={table} noun="changes" />
            </div>
          </div>
          <DataTable
            table={table}
            label="Changes"
            empty="No changes match."
            rowProps={({ original: { owner } }) => selectedRowProps(isSelectedRow(highlighted, owner))}
          />
        </TableLinksContext>
      )}
    </section>
  )
}
