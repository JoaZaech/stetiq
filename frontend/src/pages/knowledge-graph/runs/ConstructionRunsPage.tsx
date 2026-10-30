import { useMemo, useState } from 'react'
import { type ConstructionRun, useRuns } from '@/api/runs'
import { knowledgeGraphSection } from '@/app/knowledge-graph-sections'
import { ColumnPicker } from '@/components/ColumnPicker'
import { DataTable } from '@/components/DataTable'
import { ErrorAlert } from '@/components/ErrorAlert'
import { Skeleton } from '@/components/ui/skeleton'
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'
import { KnowledgeGraphSectionPage } from '../KnowledgeGraphSectionPage'
import { useKnowledgeGraphName } from '../params'
import { useRunListParams } from './run-list-params'
import { metricColumnId, paramColumnId, useRunTable } from './run-table'
import {
  filterRuns,
  RUN_STATUS_FILTERS,
  RUN_TIME_RANGES,
  runKeys,
  type RunStatusFilter,
  type RunTimeRange,
} from './runs'

const SECTION = knowledgeGraphSection('runs')

const STATUS_LABELS: Record<RunStatusFilter, string> = {
  all: 'All',
  running: 'Running',
  finished: 'Finished',
  failed: 'Failed',
}

/** `/kg/:name/runs`: the Knowledge Graph's Construction Runs, newest first. */
export function ConstructionRunsPage() {
  return (
    <KnowledgeGraphSectionPage section={SECTION}>
      <RunList />
    </KnowledgeGraphSectionPage>
  )
}

function RunList() {
  const name = useKnowledgeGraphName()
  const runs = useRuns(name)
  if (runs.isError) return <ErrorAlert error={runs.error} />
  if (runs.isPending) return <Skeleton className="h-32 w-full" />
  if (runs.data.length === 0) return <EmptyState name={name} />
  return <RunTable runs={runs.data} />
}

function RunTable({ runs }: { runs: ConstructionRun[] }) {
  const { filters, setFilter, columns, setColumn } = useRunListParams()
  // Durations of running runs and the time range are measured from when the list loaded.
  const [now] = useState(() => Date.now())
  const filtered = useMemo(() => filterRuns(runs, filters, now), [runs, filters, now])
  const keys = useMemo(() => runKeys(runs), [runs])
  const table = useRunTable({ runs: filtered, ...keys, visible: columns, now })

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-3">
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
              {STATUS_LABELS[status]}
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
        <div className="ml-auto">
          <ColumnPicker
            groups={[
              { label: 'Params', columns: keys.params.map((k) => ({ id: paramColumnId(k), label: k })) },
              { label: 'Metrics', columns: keys.metrics.map((k) => ({ id: metricColumnId(k), label: k })) },
            ]}
            visible={columns}
            onToggle={setColumn}
          />
        </div>
      </div>
      <DataTable table={table} label="Construction Runs" empty="No Construction Run matches these filters." />
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
