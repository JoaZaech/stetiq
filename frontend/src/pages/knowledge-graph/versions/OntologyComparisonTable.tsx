import { useMemo } from 'react'
import { Search } from 'lucide-react'
import { useSearchParams } from 'react-router'
import { ClassificationBadge } from '@/components/OntologyDiff'
import { DataTable, DataTableRowCount } from '@/components/DataTable'
import { ErrorAlert } from '@/components/ErrorAlert'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Skeleton } from '@/components/ui/skeleton'
import { createDataTableColumnHelper, filterColumn, useDataTable } from '@/lib/data-table'
import { type DataTableParamsOptions, useDataTableParams } from '@/lib/data-table-params'
import { formatCount } from '@/lib/format'
import { type ComparisonRow, comparisonRows } from './comparison-rows'
import { useConceptSelection, useShowOnMap } from './concept-selection'
import { ChangeLevelBadge } from './MapChangeSummary'
import type { OntologyComparison } from './ontology-map-comparison'
import { compareLevels, summarizeChanges } from './ontology-map-summary'
import type { TableLinks } from './table-links'
import { TableLinksContext } from './table-links'
import { ShowOnMap } from './TableLinks'
import { useOntologyComparison } from './use-ontology-comparison'

/** Shows the documentation-only changes, which the grid leaves out by default. */
const DOCUMENTATION_PARAM = 'changes.docs'

const column = createDataTableColumnHelper<ComparisonRow>()

const columns = column.columns([
  column.accessor('concept', {
    header: 'Concept',
    ...filterColumn('text'),
    cell: ({ getValue }) => <span className="font-mono text-xs">{getValue()}</span>,
  }),
  column.accessor('conceptKind', { header: 'Concept kind', ...filterColumn('values') }),
  column.accessor('change', { header: 'Change', ...filterColumn('values') }),
  column.accessor('level', {
    header: 'Severity',
    ...filterColumn('values'),
    // The weightiest first when sorted descending, as the rows come.
    sortFn: (a, b) => compareLevels(a.original.level, b.original.level),
    sortDescFirst: true,
    cell: ({ getValue }) => <ChangeLevelBadge level={getValue()} />,
  }),
  column.accessor('detail', { header: 'Detail', ...filterColumn('text'), enableSorting: false }),
  column.display({
    id: 'map',
    header: '',
    cell: ({ row }) => row.original.owner && <ShowOnMap concept={row.original.owner} />,
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
  const showDocumentation = params.get(DOCUMENTATION_PARAM) === '1'
  const documentationOnly = all.filter((r) => r.level === 'documentation-only').length
  const rows = useMemo(
    () => (showDocumentation ? all : all.filter((r) => r.level !== 'documentation-only')),
    [all, showDocumentation],
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
  const showOnMap = useShowOnMap()
  const links = useMemo(
    (): TableLinks => ({
      select: setSelection,
      // The grid has no attribute groups to open.
      openGroup: () => {},
      showOnMap,
    }),
    [setSelection, showOnMap],
  )
  const setShowDocumentation = (show: boolean) =>
    setParams(
      (p) => {
        if (show) p.set(DOCUMENTATION_PARAM, '1')
        else p.delete(DOCUMENTATION_PARAM)
        return p
      },
      { replace: true },
    )

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
            <p className="text-muted-foreground">{counts.map((c) => `${c.count} ${c.level}`).join(' · ')}</p>
          </div>
          <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2">
            <div className="relative w-full max-w-sm">
              <Search
                className="absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-muted-foreground"
                aria-hidden
              />
              <Input
                type="search"
                aria-label="Search changes"
                placeholder="Search changes"
                className="pl-8"
                value={table.store.state.globalFilter ?? ''}
                onChange={(e) => table.setGlobalFilter(e.target.value)}
              />
            </div>
            <div className="flex items-center gap-3">
              {documentationOnly > 0 && (
                <p className="text-xs text-muted-foreground">
                  {!showDocumentation && `${formatCount(documentationOnly, 'documentation-only change')} hidden`}
                  <Button
                    variant="link"
                    size="sm"
                    className="h-auto px-1.5 text-xs"
                    onClick={() => setShowDocumentation(!showDocumentation)}
                  >
                    {showDocumentation ? 'Hide documentation-only changes' : 'Show documentation-only changes'}
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
            rowProps={(row) => {
              const { owner } = row.original
              const current =
                owner !== null &&
                (selection?.kind === 'class' || selection?.kind === 'relation') &&
                selection.kind === owner.kind &&
                selection.label === owner.label
              return { 'aria-current': current || undefined, 'data-state': current ? 'selected' : undefined }
            }}
          />
        </TableLinksContext>
      )}
    </section>
  )
}
