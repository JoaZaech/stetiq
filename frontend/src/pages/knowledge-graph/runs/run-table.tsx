import { useMemo } from 'react'
import { Link } from 'react-router'
import type { ConstructionRun } from '@/api/runs'
import { kgUrl } from '@/app/knowledge-graph-sections'
import { RunStatusLabel } from '@/components/RunStatusLabel'
import { Checkbox } from '@/components/ui/checkbox'
import { createDataTableColumnHelper, useDataTable } from '@/lib/data-table'
import { formatDateTime, formatMetric } from '@/lib/format'
import { metricColumnId, paramColumnId } from '@/lib/metric-view-params'
import { formatDuration, runDurationMs, shortRunId } from './runs'

/** One row of the run table. */
export interface RunRow {
  run: ConstructionRun
  durationMs: number
}

const column = createDataTableColumnHelper<RunRow>()
const linkClass = 'text-primary underline-offset-4 hover:underline'
const none = <span className="text-muted-foreground">—</span>

function versionLink(kg: string, number: number | null) {
  if (number === null) return none
  return (
    <Link to={kgUrl(kg, 'versions', number)} className={linkClass}>
      v{number}
    </Link>
  )
}

const baseColumns = column.columns([
  column.display({
    id: 'select',
    header: ({ table }) => (
      <Checkbox
        aria-label="Select all runs"
        checked={table.getIsAllRowsSelected() || (table.getIsSomeRowsSelected() && 'indeterminate')}
        onCheckedChange={(checked) => table.toggleAllRowsSelected(checked === true)}
      />
    ),
    cell: ({ row }) => (
      <Checkbox
        aria-label={`Select run ${shortRunId(row.original.run.id)}`}
        checked={row.getIsSelected()}
        onCheckedChange={(checked) => row.toggleSelected(checked === true)}
      />
    ),
  }),
  column.accessor((r) => r.run.id, {
    id: 'id',
    header: 'Run',
    enableSorting: false,
    cell: ({ row }) => {
      const { id, knowledge_graph } = row.original.run
      return (
        <Link to={kgUrl(knowledge_graph, 'runs', id)} title={id} className={`font-mono ${linkClass}`}>
          {shortRunId(id)}
        </Link>
      )
    },
  }),
  column.accessor((r) => r.run.status, {
    id: 'status',
    header: 'Status',
    cell: ({ getValue }) => <RunStatusLabel status={getValue()} />,
  }),
  column.accessor((r) => r.run.started_at, {
    id: 'started',
    header: 'Started',
    sortFn: 'datetime',
    cell: ({ getValue }) => <time dateTime={getValue()}>{formatDateTime(getValue())}</time>,
  }),
  column.accessor((r) => r.durationMs, {
    id: 'duration',
    header: 'Duration',
    cell: ({ getValue }) => <span className="tabular-nums">{formatDuration(getValue())}</span>,
  }),
  column.accessor((r) => r.run.ontology_version, {
    id: 'declared',
    header: 'Declared Ontology',
    cell: ({ row, getValue }) => versionLink(row.original.run.knowledge_graph, getValue()),
  }),
  column.accessor((r) => r.run.conformance?.score, {
    id: 'conformance',
    header: 'Conformance',
    sortUndefined: 'last',
    cell: ({ getValue }) => {
      const score = getValue()
      return score === undefined ? none : <span className="tabular-nums">{formatMetric(score)}</span>
    },
  }),
  column.accessor((r) => r.run.candidate_version ?? undefined, {
    id: 'candidate',
    header: 'Candidate',
    sortUndefined: 'last',
    cell: ({ row }) => versionLink(row.original.run.knowledge_graph, row.original.run.candidate_version),
  }),
])

/**
 * The run table over `runs` (already filtered), with a selection column and one
 * optional column per param and metric key; `visible` names the optional columns shown
 * (`paramColumnId`/`metricColumnId`). Read the selection with
 * `table.getSelectedRowModel()` (row ids are run ids), e.g. to compare runs.
 */
export function useRunTable({
  runs,
  params,
  metrics,
  visible,
  now,
}: {
  runs: readonly ConstructionRun[]
  params: readonly string[]
  metrics: readonly string[]
  visible: ReadonlySet<string>
  /** The time running runs' durations are measured to. */
  now: number
}) {
  const columns = useMemo(
    () =>
      column.columns([
        ...baseColumns,
        ...params.map((key) =>
          column.accessor((r) => r.run.params[key], {
            id: paramColumnId(key),
            header: key,
            sortUndefined: 'last',
            cell: ({ getValue }) => getValue() ?? none,
          }),
        ),
        ...metrics.map((key) =>
          column.accessor((r) => r.run.metrics[key], {
            id: metricColumnId(key),
            header: key,
            sortUndefined: 'last',
            cell: ({ getValue }) => {
              const value = getValue()
              return value === undefined ? none : <span className="tabular-nums">{formatMetric(value)}</span>
            },
          }),
        ),
      ]),
    [params, metrics],
  )
  const data = useMemo(
    () => runs.map((run): RunRow => ({ run, durationMs: runDurationMs(run, now) })),
    [runs, now],
  )
  const columnVisibility = useMemo(
    () =>
      Object.fromEntries([
        ...params.map((k) => [paramColumnId(k), visible.has(paramColumnId(k))]),
        ...metrics.map((k) => [metricColumnId(k), visible.has(metricColumnId(k))]),
      ]),
    [params, metrics, visible],
  )
  return useDataTable({
    data,
    columns,
    getRowId: (row) => row.run.id,
    state: { columnVisibility },
    initialState: { sorting: [{ id: 'started', desc: true }] },
  })
}
