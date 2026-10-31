import { useQuery } from '@tanstack/react-query'
import { lazy, type ReactNode, Suspense, useMemo, useState } from 'react'
import { useNavigate } from 'react-router'
import { useGatePreviews } from '@/api/gate-previews'
import { gateResultsQuery } from '@/api/gate-results'
import { type ConstructionRun, useAllRunEvaluations, useRuns } from '@/api/runs'
import { kgCompareUrl, knowledgeGraphSection } from '@/app/knowledge-graph-sections'
import { ColumnPicker } from '@/components/ColumnPicker'
import { CompareToolbar } from '@/components/CompareToolbar'
import { DataTable } from '@/components/DataTable'
import { ErrorAlert } from '@/components/ErrorAlert'
import { RUN_STATUSES } from '@/components/run-status'
import { ViewModeToggle } from '@/components/ViewModeToggle'
import { Skeleton } from '@/components/ui/skeleton'
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'
import { formatDateTime } from '@/lib/format'
import {
  metricColumnId,
  paramColumnId,
  useChartSearch,
  useShownColumns,
  useViewMode,
  type ViewMode,
} from '@/lib/metric-view-params'
import { KnowledgeGraphSectionPage } from '../KnowledgeGraphSectionPage'
import { useKnowledgeGraphName } from '../params'
import { type Kpi, runChartSeries } from './compare'
import { GatePreviewNote } from './gate-verdicts'
import { KpiSheet, type KpiSelection } from './kpi-sheet'
import { useRunFilters } from './run-list-params'
import { useRunTable } from './run-table'
import {
  filterRuns,
  RUN_STATUS_FILTERS,
  RUN_TIME_RANGES,
  runKeys,
  type RunStatusFilter,
  type RunTimeRange,
} from './runs'

const SECTION = knowledgeGraphSection('runs')

const statusFilterLabel = (status: RunStatusFilter) =>
  status === 'all' ? 'All' : RUN_STATUSES[status].label

/**
 * `/kg/:name/runs`: the Knowledge Graph's Construction Runs, newest first, as a table
 * (select runs to compare them) or as one chart per run metric, Conformance and Evaluator
 * result metric.
 */
export function ConstructionRunsPage() {
  const [mode, setMode] = useViewMode()
  return (
    <KnowledgeGraphSectionPage section={SECTION} actions={<ViewModeToggle mode={mode} onChange={setMode} />}>
      <RunList mode={mode} />
    </KnowledgeGraphSectionPage>
  )
}

function RunList({ mode }: { mode: ViewMode }) {
  const name = useKnowledgeGraphName()
  const runs = useRuns(name)
  if (runs.isError) return <ErrorAlert error={runs.error} />
  if (runs.isPending) return <Skeleton className="h-32 w-full" />
  if (runs.data.length === 0) return <EmptyState name={name} />
  return <FilteredRuns runs={runs.data} mode={mode} />
}

/** The status and time-range filters, over both the table and the charts. */
function FilteredRuns({ runs, mode }: { runs: ConstructionRun[]; mode: ViewMode }) {
  const { filters, setFilter } = useRunFilters()
  // Durations of running runs and the time range are measured from when the list loaded.
  const [now] = useState(() => Date.now())
  const filtered = useMemo(() => filterRuns(runs, filters, now), [runs, filters, now])
  const [selection, setSelection] = useState<KpiSelection | null>(null)

  const filterControls = (
    <>
      <ToggleGroup
        type="single"
        variant="outline"
        size="sm"
        aria-label="Status"
        value={filters.status}
        onValueChange={(value) => value && setFilter('status', value as RunStatusFilter)}
      >
        {RUN_STATUS_FILTERS.map((status) => (
          <ToggleGroupItem key={status} value={status}>
            {statusFilterLabel(status)}
          </ToggleGroupItem>
        ))}
      </ToggleGroup>
      <ToggleGroup
        type="single"
        variant="outline"
        size="sm"
        aria-label="Started"
        value={filters.range}
        onValueChange={(value) => value && setFilter('range', value as RunTimeRange)}
      >
        {RUN_TIME_RANGES.map((range) => (
          <ToggleGroupItem key={range.value} value={range.value}>
            {range.label}
          </ToggleGroupItem>
        ))}
      </ToggleGroup>
    </>
  )

  if (mode === 'chart') {
    return (
      <div className="space-y-3">
        <div className="flex flex-wrap items-center gap-3">{filterControls}</div>
        <RunCharts runs={filtered} onPointClick={(runId, kpi) => setSelection({ runId, kpi })} />
        <KpiSheet knowledgeGraph={runs[0].knowledge_graph} selection={selection} onClose={() => setSelection(null)} />
      </div>
    )
  }
  return <RunTable runs={runs} filtered={filtered} now={now} filterControls={filterControls} />
}

function RunTable({
  runs,
  filtered,
  now,
  filterControls,
}: {
  runs: ConstructionRun[]
  filtered: ConstructionRun[]
  now: number
  filterControls: ReactNode
}) {
  const name = useKnowledgeGraphName()
  const [shownColumns, setShownColumn] = useShownColumns()
  // Every key over all runs, so a filter never drops a column.
  const keys = useMemo(() => runKeys(runs), [runs])
  const table = useRunTable({ runs: filtered, ...keys, visible: shownColumns, now })
  const navigate = useNavigate()
  const selected = table.getSelectedRowModel().rows.map((row) => row.original.run)
  const compare = () => {
    const oldestFirst = [...selected].sort((a, b) => Date.parse(a.started_at) - Date.parse(b.started_at))
    navigate(kgCompareUrl(name, 'runs', oldestFirst.map((run) => run.id)))
  }

  return (
    <div className="space-y-3">
      <CompareToolbar
        selected={selected.length}
        needs="many"
        noun="runs"
        readyHint="The selected runs side by side"
        onCompare={compare}
      >
        {filterControls}
        <div className="ml-auto">
          <ColumnPicker
            groups={[
              { label: 'Params', columns: keys.params.map((k) => ({ id: paramColumnId(k), label: k })) },
              { label: 'Metrics', columns: keys.metrics.map((k) => ({ id: metricColumnId(k), label: k })) },
            ]}
            visible={shownColumns}
            onToggle={setShownColumn}
          />
        </div>
      </CompareToolbar>
      <DataTable table={table} label="Construction Runs" empty="No Construction Run matches these filters." />
    </div>
  )
}

// Recharts is large: load the chart grid only when the chart view is opened.
const MetricChartGrid = lazy(() => import('@/components/MetricChartGrid'))

const RUN_X_AXIS = {
  label: 'Started',
  format: (x: number) => formatDateTime(new Date(x).toISOString()),
  scale: 'time',
} as const

/**
 * One chart per run metric, Conformance and Evaluator result metric (one per Evaluator
 * parameter configuration), over the runs' start times. A gated KPI's chart draws its Gate
 * bounds and colours each point pass or fail by the compare page's verdict.
 * `onPointClick` is called with the clicked point's run and the chart's KPI.
 */
function RunCharts({
  runs,
  onPointClick,
}: {
  runs: ConstructionRun[]
  onPointClick?: (runId: string, kpi: Kpi) => void
}) {
  const name = useKnowledgeGraphName()
  const evaluations = useAllRunEvaluations(name)
  const gateResults = useQuery(gateResultsQuery(name))
  const gatePreviews = useGatePreviews(name)
  const [search, setSearch] = useChartSearch()
  const series = useMemo(
    () => runChartSeries(runs, evaluations.data ?? [], gateResults.data ?? [], gatePreviews.data ?? []),
    [runs, evaluations.data, gateResults.data, gatePreviews.data],
  )
  const failed = [evaluations, gateResults, gatePreviews].find((q) => q.isError)
  if (failed) return <ErrorAlert error={failed.error} />
  if (evaluations.isPending || gateResults.isPending || gatePreviews.isPending) {
    return <Skeleton className="h-64 w-full" />
  }
  const source = gatePreviews.data?.[0]?.source
  return (
    <div className="space-y-3">
      {source !== undefined && <GatePreviewNote knowledgeGraph={name} source={source} />}
      <Suspense fallback={<Skeleton className="h-64 w-full" />}>
        <MetricChartGrid
          series={series}
          xAxis={RUN_X_AXIS}
          search={search}
          onSearchChange={setSearch}
          onPointClick={
            onPointClick &&
            ((s, point) => {
              // The lazy grid loses its series type: find the clicked chart's KPI by metric.
              const kpi = series.find((x) => x.metric === s.metric)?.kpi
              if (point.id !== undefined && kpi !== undefined) onPointClick(point.id, kpi)
            })
          }
        />
      </Suspense>
    </div>
  )
}

const SNIPPET = (name: string) => `import stetiq

client = stetiq.Client()
with client.start_run(${JSON.stringify(name)}, alias="production") as run:
    run.log_params({"extractor": "llm"})
    ...  # your extraction workflow; the run observes the graph when the block ends`

function EmptyState({ name }: { name: string }) {
  return (
    <div className="rounded-lg border border-dashed p-8">
      <h3 className="text-base font-semibold">No Construction Runs yet</h3>
      <p className="mt-1 max-w-prose text-sm text-muted-foreground">
        A Construction Run records one execution of your extraction workflow against a Declared
        Ontology, from the Python SDK: its params and metrics, and the Observation it ends with.
      </p>
      <pre className="mt-4 overflow-x-auto rounded-md bg-muted p-4 text-sm">
        <code className="font-mono">{SNIPPET(name)}</code>
      </pre>
    </div>
  )
}
