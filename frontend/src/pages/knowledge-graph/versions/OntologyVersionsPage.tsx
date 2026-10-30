import { lazy, Suspense, useMemo, type ReactNode } from 'react'
import { Link, useNavigate } from 'react-router'
import {
  type Alias,
  type Promotion,
  useAliases,
  useContractAlias,
  usePromotions,
} from '@/api/aliases'
import { useOntologyVersions, type OntologyVersion } from '@/api/ontology-versions'
import { knowledgeGraphSection, kgUrl } from '@/app/knowledge-graph-sections'
import { DataTable } from '@/components/DataTable'
import { ErrorAlert } from '@/components/ErrorAlert'
import { MetricColumnsPicker } from '@/components/MetricColumnsPicker'
import { ViewModeToggle } from '@/components/ViewModeToggle'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Skeleton } from '@/components/ui/skeleton'
import { createDataTableColumnHelper, useDataTable } from '@/lib/data-table'
import { formatDateTime, formatMetric } from '@/lib/format'
import { metricSeries } from '@/lib/metric-charts'
import { useChartSearch, useMetricColumns, useViewMode } from '@/lib/metric-view-params'
import { KnowledgeGraphSectionPage } from '../KnowledgeGraphSectionPage'
import { useKnowledgeGraphName } from '../params'
import { AliasChips, CandidateBadge } from './AliasChips'
import { aliasesByVersion, candidateVersions } from './lineage'
import { type VersionMetrics, useVersionMetrics } from './version-metrics'

const SECTION = knowledgeGraphSection('versions')

/** One row of the version table. */
interface VersionRow {
  knowledgeGraph: string
  number: number
  origin: OntologyVersion['origin']
  createdAt: string
  aliases: string[]
  contractAlias: string | undefined
  candidate: boolean
  /** Evaluator metrics by `<evaluator>/<metric>` (see `evaluatorMetrics`). */
  metrics: Readonly<Record<string, number>>
}

const column = createDataTableColumnHelper<VersionRow>()

const columns = column.columns([
  // Select two rows, then Compare: the Ontology Diff between them.
  column.display({
    id: 'select',
    header: () => <span className="sr-only">Select</span>,
    enableSorting: false,
    cell: ({ row }) => (
      <Checkbox
        aria-label={`Select v${row.original.number}`}
        checked={row.getIsSelected()}
        onCheckedChange={(checked) => row.toggleSelected(checked === true)}
      />
    ),
  }),
  column.accessor('number', {
    header: 'Version',
    cell: ({ row }) => (
      <Link
        to={kgUrl(row.original.knowledgeGraph, 'versions', row.original.number)}
        className="font-medium text-primary underline-offset-4 hover:underline"
      >
        v{row.original.number}
      </Link>
    ),
  }),
  column.accessor('origin', { header: 'Origin' }),
  column.accessor('createdAt', {
    header: 'Created',
    sortFn: 'datetime',
    cell: ({ getValue }) => <time dateTime={getValue()}>{formatDateTime(getValue())}</time>,
  }),
  column.display({
    id: 'aliases',
    header: 'Aliases',
    cell: ({ row }) => (
      <span className="inline-flex flex-wrap items-center gap-1">
        <AliasChips aliases={row.original.aliases} contractAlias={row.original.contractAlias} />
        {row.original.candidate && <CandidateBadge />}
      </span>
    ),
  }),
])

/** A column for one Evaluator metric; a version without it shows a dash and sorts last. */
function metricColumn(metric: string) {
  return column.accessor((row) => row.metrics[metric], {
    id: metric,
    header: metric,
    sortFn: 'basic',
    sortUndefined: 'last',
    cell: ({ getValue }) => {
      const value = getValue()
      return value === undefined ? (
        <span className="text-muted-foreground">—</span>
      ) : (
        <span className="tabular-nums">{formatMetric(value)}</span>
      )
    },
  })
}

const NO_METRICS: Readonly<Record<string, number>> = {}

/**
 * `/kg/:name/versions`: the Knowledge Graph's Ontology Versions, newest first, as a table
 * with optional Evaluator metric columns, or as one chart per Evaluator metric.
 */
export function OntologyVersionsPage() {
  const name = useKnowledgeGraphName()
  const versions = useOntologyVersions(name)
  const aliases = useAliases(name)
  const promotions = usePromotions(name)
  const contractAlias = useContractAlias(name)
  const metrics = useVersionMetrics(name, versions.data)
  const [mode, setMode] = useViewMode()
  const [metricColumns, setMetricColumns] = useMetricColumns()

  const actions = (
    <>
      {mode === 'table' && (
        <MetricColumnsPicker
          heading="Evaluator metrics"
          metrics={metrics.names}
          selected={metricColumns}
          onChange={setMetricColumns}
        />
      )}
      <ViewModeToggle mode={mode} onChange={setMode} />
    </>
  )

  let content: ReactNode
  if (versions.isError || aliases.isError || promotions.isError || metrics.error) {
    content = <ErrorAlert error={versions.error ?? aliases.error ?? promotions.error ?? metrics.error} />
  } else if (versions.isPending || aliases.isPending || promotions.isPending || metrics.isPending) {
    content = <Skeleton className="h-32 w-full" />
  } else if (versions.data.length === 0) {
    content = <p className="text-sm text-muted-foreground">No Ontology Versions yet.</p>
  } else if (mode === 'chart') {
    content = <VersionCharts versions={versions.data} metrics={metrics} />
  } else {
    content = (
      <VersionTable
        name={name}
        versions={versions.data}
        aliases={aliases.data}
        promotions={promotions.data}
        contractAlias={contractAlias.data}
        metrics={metrics}
        metricColumns={metricColumns}
      />
    )
  }
  return (
    <KnowledgeGraphSectionPage section={SECTION} actions={actions}>
      {content}
    </KnowledgeGraphSectionPage>
  )
}

function VersionTable({
  name,
  versions,
  aliases,
  promotions,
  contractAlias,
  metrics,
  metricColumns,
}: {
  name: string
  versions: OntologyVersion[]
  aliases: Alias[]
  promotions: Promotion[]
  contractAlias: string | undefined
  metrics: VersionMetrics
  metricColumns: string[]
}) {
  // Rows stay referentially stable between renders, as `useDataTable` needs.
  const data = useMemo(() => {
    const aliased = aliasesByVersion(aliases)
    const candidates = candidateVersions(versions, promotions)
    return versions.map(
      (v): VersionRow => ({
        knowledgeGraph: name,
        number: v.number,
        origin: v.origin,
        createdAt: v.created_at,
        aliases: aliased.get(v.number) ?? [],
        contractAlias,
        candidate: candidates.has(v.number),
        metrics: metrics.byVersion.get(v.number) ?? NO_METRICS,
      }),
    )
  }, [name, versions, aliases, promotions, contractAlias, metrics])
  // Every metric has a column, in name order; only the chosen ones are visible.
  const allColumns = useMemo(
    () => column.columns([...columns, ...metrics.names.map(metricColumn)]),
    [metrics],
  )
  const columnVisibility = useMemo(
    () => Object.fromEntries(metrics.names.map((m) => [m, metricColumns.includes(m)])),
    [metrics, metricColumns],
  )
  const table = useDataTable({
    data,
    columns: allColumns,
    getRowId: (row) => String(row.number),
    state: { columnVisibility },
    initialState: { sorting: [{ id: 'number', desc: true }] },
  })
  const navigate = useNavigate()
  const selected = table.getSelectedRowModel().rows.map((row) => row.original.number)
  const compare = () => {
    const [base, target] = [...selected].sort((a, b) => a - b)
    navigate(`${kgUrl(name, 'versions', 'compare')}?base=${base}&target=${target}`)
  }
  return (
    <div className="space-y-3">
      <div className="flex items-center gap-3">
        <Button size="sm" variant="outline" disabled={selected.length !== 2} onClick={compare}>
          Compare
        </Button>
        <span className="text-xs text-muted-foreground">
          {selected.length === 2
            ? 'Ontology Diff from the older to the newer version'
            : 'Select two versions to compare'}
        </span>
      </div>
      <DataTable table={table} label="Ontology Versions" empty="No Ontology Versions yet." />
    </div>
  )
}

// Recharts is large: load the chart grid only when the chart view is opened.
const MetricChartGrid = lazy(() => import('@/components/MetricChartGrid'))

function VersionCharts({ versions, metrics }: { versions: OntologyVersion[]; metrics: VersionMetrics }) {
  const [search, setSearch] = useChartSearch()
  const series = useMemo(
    () =>
      metricSeries(
        versions.map((v) => ({ x: v.number, metrics: metrics.byVersion.get(v.number) ?? NO_METRICS })),
      ),
    [versions, metrics],
  )
  const xAxis = useMemo(
    () => ({
      label: 'Ontology Version',
      format: (x: number) => `v${x}`,
      ticks: versions.map((v) => v.number).sort((a, b) => a - b),
    }),
    [versions],
  )
  return (
    <Suspense fallback={<Skeleton className="h-64 w-full" />}>
      <MetricChartGrid series={series} xAxis={xAxis} search={search} onSearchChange={setSearch} />
    </Suspense>
  )
}
