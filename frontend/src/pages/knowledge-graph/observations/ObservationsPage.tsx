import { lazy, Suspense, useId, useMemo } from 'react'
import { Link } from 'react-router'
import {
  type DriftEvent,
  type Observation,
  useAlignmentTrend,
  useDriftEvents,
  useObservations,
} from '@/api/observations'
import { knowledgeGraphSection, kgUrl } from '@/app/knowledge-graph-sections'
import { ErrorAlert } from '@/components/ErrorAlert'
import { FilterMenu } from '@/components/FilterMenu'
import { InfoTip } from '@/components/InfoTip'
import { KpiTiles } from '@/components/KpiTiles'
import { ListCount, ListToolbar } from '@/components/ListToolbar'
import { StatusLabel } from '@/components/StatusLabel'
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from '@/components/ui/sheet'
import { Skeleton } from '@/components/ui/skeleton'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { useSearchParam } from '@/hooks/use-search-param'
import { formatDateTime, formatPercent } from '@/lib/format'
import { helpUrl } from '@/pages/help/guide-index'
import type { MetricSeries } from '@/lib/metric-charts'
import { useSheetParam } from '@/lib/sheet-param'
import { evaluationKpis } from '../evaluation/evaluation-kpis'
import { findingsFromDrift } from '../evaluation/findings'
import { FindingsTable } from '../evaluation/FindingsTable'
import { KnowledgeGraphSectionPage } from '../KnowledgeGraphSectionPage'
import { useKnowledgeGraphName } from '../params'
import { shortRunId } from '../runs/runs'
import { focusSheetItself } from '../use-case/sheet-focus'
import { alignmentSeries } from './alignment-trend'
import {
  filterObservationRows,
  formatThresholds,
  notComparableRows,
  OBSERVATION_STATUSES,
  type ObservationRow,
  observationRows,
} from './observation-rows'

const SECTION = knowledgeGraphSection('observations')
const DRIFT_GUIDE = `${helpUrl('concepts')}#observation-and-drift`
const SHEET_KINDS = ['observation'] as const

// Recharts is large: load the chart only on this page.
const MetricChart = lazy(() => import('@/components/MetricChartGrid').then((m) => ({ default: m.MetricChart })))

const ALIGNMENT_TREND_GUIDE = `${helpUrl('using-the-web-ui')}#observations`

const TREND_X_AXIS = {
  label: 'Observed',
  format: (x: number) => formatDateTime(new Date(x).toISOString()),
  scale: 'time',
} as const

/**
 * `/kg/:name/observations`: the alignment trend (run and on-demand Conformance scores
 * over time), then when the Graph Source was inspected, newest first, as a table; a row
 * opens a sheet with its Conformance and Drift (`?sheet=observation:<id>`). Read-only: an
 * Observation needs graph credentials, which never leave the SDK process (`stetiq observe`).
 */
export function ObservationsPage() {
  return (
    <KnowledgeGraphSectionPage section={SECTION}>
      <ObservationList />
    </KnowledgeGraphSectionPage>
  )
}

function ObservationList() {
  const name = useKnowledgeGraphName()
  const observations = useObservations(name)
  const driftEvents = useDriftEvents(name)
  const trend = useAlignmentTrend(name)
  const [query, setQuery] = useSearchParam()
  const [status, setStatus] = useSearchParam('status')
  const { sheet, openSheet, closeSheet } = useSheetParam(SHEET_KINDS)
  const rows = useMemo(
    () => observationRows(observations.data ?? [], driftEvents.data ?? [], trend.data ?? []),
    [observations.data, driftEvents.data, trend.data],
  )
  const series = useMemo(() => alignmentSeries(trend.data ?? []), [trend.data])
  const shown = useMemo(() => filterObservationRows(rows, query, status), [rows, query, status])

  if (observations.isError || driftEvents.isError || trend.isError) {
    return <ErrorAlert error={observations.error ?? driftEvents.error ?? trend.error} />
  }
  if (observations.isPending || driftEvents.isPending || trend.isPending) return <Skeleton className="h-32 w-full" />
  if (rows.length === 0) {
    return (
      <p className="text-sm text-muted-foreground">
        No Observations yet. Run <code className="font-mono">stetiq observe</code> or end a Construction Run.
      </p>
    )
  }
  const statusCounts = OBSERVATION_STATUSES.map((s) => [s, rows.filter((r) => r.status === s).length] as const)
  const open = sheet && rows.find((r) => r.observation.id === sheet.id)
  return (
    <div className="space-y-3">
      <AlignmentTrend series={series} onOpen={(id) => openSheet({ kind: 'observation', id })} />
      <ListToolbar search={query} onSearch={setQuery} searchLabel="Search Observations">
        <FilterMenu label="Status" value={status} options={statusCounts} onChange={setStatus} />
      </ListToolbar>
      <Table aria-label="Observations">
        <TableHeader>
          <TableRow>
            <TableHead>Time</TableHead>
            <TableHead>Status</TableHead>
            <TableHead>Source</TableHead>
            <TableHead>Ontology Version</TableHead>
            <TableHead className="text-right">Conformance</TableHead>
            <TableHead className="text-right">Findings</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {shown.length === 0 ? (
            <TableRow>
              <TableCell colSpan={6} className="text-muted-foreground">
                No Observation matches these filters.
              </TableCell>
            </TableRow>
          ) : (
            shown.map((row) => (
              <ObservationTableRow
                key={row.observation.id}
                name={name}
                row={row}
                onOpen={() => openSheet({ kind: 'observation', id: row.observation.id })}
              />
            ))
          )}
        </TableBody>
      </Table>
      <ListCount shown={shown.length} total={rows.length} noun="Observations" />
      <ObservationSheet name={name} row={open || undefined} onClose={closeSheet} />
    </div>
  )
}

/**
 * The alignment trend: one Conformance line, run points filled and on-demand ones hollow.
 * A point opens its Observation's sheet. No threshold, so no bound is drawn.
 */
function AlignmentTrend({ series, onOpen }: { series: MetricSeries; onOpen: (observationId: string) => void }) {
  return (
    <section aria-labelledby="alignment-trend" className="space-y-2">
      <h3 id="alignment-trend" className="flex items-center gap-1.5 text-sm font-semibold">
        Alignment trend
        <InfoTip label="the alignment trend" to={ALIGNMENT_TREND_GUIDE}>
          The Conformance score of each Construction Run and on-demand Observation, over time. It has no threshold
          and raises no Drift.
        </InfoTip>
      </h3>
      {series.points.length === 0 ? (
        <p className="text-sm text-muted-foreground">No Conformance scores yet.</p>
      ) : (
        <Suspense fallback={<Skeleton className="h-52 w-full" />}>
          <MetricChart
            series={series}
            xAxis={TREND_X_AXIS}
            onPointClick={(point) => point.id !== undefined && onOpen(point.id)}
          />
        </Suspense>
      )}
    </section>
  )
}

function ObservationTableRow({ name, row, onOpen }: { name: string; row: ObservationRow; onOpen: () => void }) {
  const { observation, drift, alignment } = row
  const version = alignment?.ontology_version ?? drift?.ontology_version
  return (
    <TableRow className="cursor-pointer" onClick={onOpen}>
      <TableCell>
        <button
          type="button"
          className="text-primary underline-offset-4 hover:underline"
          onClick={(e) => {
            e.stopPropagation()
            onOpen()
          }}
        >
          <time dateTime={observation.observed_at}>{formatDateTime(observation.observed_at)}</time>
        </button>
      </TableCell>
      <TableCell>
        <StatusLabel tone={drift ? 'warning' : 'success'} label={row.status} />
      </TableCell>
      <TableCell>
        <Source name={name} observation={observation} />
      </TableCell>
      <TableCell>{version !== undefined ? <VersionLink name={name} number={version} /> : <Dash />}</TableCell>
      <TableCell className="text-right tabular-nums">
        {alignment ? formatPercent(alignment.score) : <span className="text-muted-foreground">no score</span>}
      </TableCell>
      <TableCell className="text-right tabular-nums">{drift ? row.findings : <Dash />}</TableCell>
    </TableRow>
  )
}

function Source({ name, observation }: { name: string; observation: Observation }) {
  if (!observation.run_id) return <span className="text-muted-foreground">on demand</span>
  return (
    <Link
      to={kgUrl(name, 'runs', observation.run_id)}
      onClick={(e) => e.stopPropagation()}
      aria-label={`Run ${shortRunId(observation.run_id)}`}
      className="font-mono text-xs text-primary underline-offset-4 hover:underline"
    >
      run {shortRunId(observation.run_id)}
    </Link>
  )
}

function VersionLink({ name, number }: { name: string; number: number }) {
  return (
    <Link
      to={kgUrl(name, 'versions', number)}
      onClick={(e) => e.stopPropagation()}
      className="text-primary underline-offset-4 hover:underline"
    >
      v{number}
    </Link>
  )
}

const Dash = () => <span className="text-muted-foreground">—</span>

/**
 * One Observation: its metadata line, the four evaluation tiles (Conformance, from its run
 * for a run-end one, and Drift apply) and its findings.
 */
function ObservationSheet({ name, row, onClose }: { name: string; row: ObservationRow | undefined; onClose: () => void }) {
  return (
    <Sheet open={row !== undefined} onOpenChange={(open) => !open && onClose()}>
      <SheetContent className="overflow-y-auto sm:max-w-2xl" onOpenAutoFocus={focusSheetItself}>
        {row && <ObservationSheetContent name={name} row={row} />}
      </SheetContent>
    </Sheet>
  )
}

function ObservationSheetContent({ name, row }: { name: string; row: ObservationRow }) {
  const { observation, drift } = row
  return (
    <>
      <SheetHeader className="gap-2 pr-12">
        <SheetDescription>Observation</SheetDescription>
        <SheetTitle>
          <time dateTime={observation.observed_at}>{formatDateTime(observation.observed_at)}</time>
        </SheetTitle>
        <p className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-foreground">
          <StatusLabel tone={drift ? 'warning' : 'success'} label={row.status} />
          <Source name={name} observation={observation} />
          {drift && <DriftMeta name={name} drift={drift} />}
          <BaselineMeta row={row} />
        </p>
      </SheetHeader>
      <div className="space-y-6 px-4 pb-6">
        <KpiTiles tiles={evaluationKpis({ conformance: row.alignment?.score, drift: row.findings })} />
        <FindingsTable rows={drift ? findingsFromDrift(drift.findings) : []} empty="No Drift." />
        <NotComparableList observation={observation} />
      </div>
    </>
  )
}

/** When its Violation Rates were compared with: the Baseline Observation's time, or "itself". */
function BaselineMeta({ row }: { row: ObservationRow }) {
  const { observation, baseline } = row
  if (observation.baseline_observation_id === null) return null
  if (observation.baseline_observation_id === observation.id) return <span>baseline: itself</span>
  return (
    <span>
      baseline:{' '}
      {baseline ? <time dateTime={baseline.observed_at}>{formatDateTime(baseline.observed_at)}</time> : 'unknown'}
    </span>
  )
}

/** The Drift checks that lacked their input; nothing when every check could run. */
function NotComparableList({ observation }: { observation: Observation }) {
  const id = useId()
  const rows = notComparableRows(observation.not_comparable)
  if (rows.length === 0) return null
  return (
    <section aria-labelledby={id} className="space-y-3">
      <h3 className="flex items-center gap-1.5 text-sm font-semibold">
        <span id={id}>Not comparable</span>
        <InfoTip label="Not comparable" to={DRIFT_GUIDE}>
          Checks that lacked their input, such as a Violation Rate the Baseline Observation cannot give or a truncated value list. They raise no Drift.
        </InfoTip>
      </h3>
      <Table aria-label="Not comparable">
        <TableHeader>
          <TableRow>
            <TableHead>Concept</TableHead>
            <TableHead>Kind</TableHead>
            <TableHead>Check</TableHead>
            <TableHead>Reason</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {rows.map((r) => (
            <TableRow key={`${r.subject} ${r.check}`}>
              <TableCell className="font-mono text-xs">{r.subject}</TableCell>
              <TableCell>{r.kind}</TableCell>
              <TableCell>{r.check}</TableCell>
              <TableCell className="text-muted-foreground">{r.reason}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </section>
  )
}

function DriftMeta({ name, drift }: { name: string; drift: DriftEvent }) {
  return (
    <>
      <span aria-label="Contract Alias">{drift.contract_alias}</span>
      <VersionLink name={name} number={drift.ontology_version} />
      <span aria-label="Thresholds">{formatThresholds(drift.thresholds)}</span>
    </>
  )
}
