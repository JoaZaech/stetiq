import { useId, useMemo } from 'react'
import { Link } from 'react-router'
import { type DriftEvent, type Observation, useDriftEvents, useObservations } from '@/api/observations'
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
import { formatDateTime } from '@/lib/format'
import { helpUrl } from '@/pages/help/guide-index'
import { useSheetParam } from '@/lib/sheet-param'
import { evaluationKpis } from '../evaluation/evaluation-kpis'
import { findingsFromDrift } from '../evaluation/findings'
import { FindingsTable } from '../evaluation/FindingsTable'
import { KnowledgeGraphSectionPage } from '../KnowledgeGraphSectionPage'
import { useKnowledgeGraphName } from '../params'
import { shortRunId } from '../runs/runs'
import { focusSheetItself } from '../use-case/sheet-focus'
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

/**
 * `/kg/:name/observations`: when the Graph Source was inspected, newest first, as a
 * table; a row opens a sheet with its Drift (`?sheet=observation:<id>`). Read-only: an
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
  const [query, setQuery] = useSearchParam()
  const [status, setStatus] = useSearchParam('status')
  const { sheet, openSheet, closeSheet } = useSheetParam(SHEET_KINDS)
  const rows = useMemo(
    () => observationRows(observations.data ?? [], driftEvents.data ?? []),
    [observations.data, driftEvents.data],
  )
  const shown = useMemo(() => filterObservationRows(rows, query, status), [rows, query, status])

  if (observations.isError || driftEvents.isError) {
    return <ErrorAlert error={observations.error ?? driftEvents.error} />
  }
  if (observations.isPending || driftEvents.isPending) return <Skeleton className="h-32 w-full" />
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
            <TableHead className="text-right">Findings</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {shown.length === 0 ? (
            <TableRow>
              <TableCell colSpan={5} className="text-muted-foreground">
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

function ObservationTableRow({ name, row, onOpen }: { name: string; row: ObservationRow; onOpen: () => void }) {
  const { observation, drift } = row
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
      <TableCell>{drift ? <VersionLink name={name} number={drift.ontology_version} /> : <Dash />}</TableCell>
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

/** One Observation: its metadata line, the four evaluation tiles (only Drift applies) and its findings. */
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
        <KpiTiles tiles={evaluationKpis({ drift: row.findings })} />
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
      <h2 className="flex items-center gap-1.5 text-sm font-semibold">
        <span id={id}>Not comparable</span>
        <InfoTip label="Not comparable" to={DRIFT_GUIDE}>
          Checks that lacked their input, such as a Violation Rate the Baseline Observation cannot give or a truncated value list. They raise no Drift.
        </InfoTip>
      </h2>
      <Table aria-label="Not comparable">
        <TableHeader>
          <TableRow>
            <TableHead>Subject</TableHead>
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
