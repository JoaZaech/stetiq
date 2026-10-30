import { useId, useMemo, type ReactNode } from 'react'
import { CircleCheck, TriangleAlert } from 'lucide-react'
import { Link } from 'react-router'
import {
  type DriftEvent,
  type DriftThresholds,
  formatScope,
  type Observation,
  useDriftEvents,
  useObservations,
} from '@/api/observations'
import { knowledgeGraphSection, kgUrl } from '@/app/knowledge-graph-sections'
import { CopyButton } from '@/components/CopyButton'
import { ErrorAlert } from '@/components/ErrorAlert'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { formatDateTime } from '@/lib/format'
import { KnowledgeGraphSectionPage } from '../KnowledgeGraphSectionPage'
import { useKnowledgeGraphName } from '../params'

const SECTION = knowledgeGraphSection('observations')

/**
 * `/kg/:name/observations`: when the Graph Source was inspected, newest first, each
 * with the Drift it found against the Contract Alias. Read-only: an Observation needs
 * graph credentials, which never leave the SDK process (`stetiq observe`).
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
  const driftByObservation = useMemo(
    () => new Map((driftEvents.data ?? []).map((e) => [e.observation_id, e])),
    [driftEvents.data],
  )

  if (observations.isError || driftEvents.isError) {
    return <ErrorAlert error={observations.error ?? driftEvents.error} />
  }
  if (observations.isPending || driftEvents.isPending) {
    return <Skeleton className="h-32 w-full" />
  }
  if (observations.data.length === 0) {
    return (
      <p className="text-sm text-muted-foreground">
        No Observations yet. Run <code className="font-mono">stetiq observe</code>, or end a
        Construction Run, to inspect the Graph Source.
      </p>
    )
  }
  const newestFirst = [...observations.data].reverse()
  return (
    <div className="space-y-4">
      {driftEvents.data.length === 0 && (
        <Alert>
          <CircleCheck aria-hidden />
          <AlertDescription>No Drift. The Knowledge Graph matches the Ontology Version of its Contract Alias.</AlertDescription>
        </Alert>
      )}
      {newestFirst.map((observation) => (
        <ObservationCard
          key={observation.id}
          name={name}
          observation={observation}
          drift={driftByObservation.get(observation.id)}
        />
      ))}
    </div>
  )
}

function ObservationCard({
  name,
  observation,
  drift,
}: {
  name: string
  observation: Observation
  drift: DriftEvent | undefined
}) {
  const id = useId()
  return (
    <article aria-labelledby={id} className="space-y-4 rounded-lg border p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 id={id} className="text-sm font-semibold">
          Observation{' '}
          <time dateTime={observation.observed_at}>{formatDateTime(observation.observed_at)}</time>
        </h3>
        {drift ? (
          <Badge variant="destructive">
            <TriangleAlert aria-hidden />
            Drift
          </Badge>
        ) : (
          <Badge variant="outline">No Drift</Badge>
        )}
      </div>
      <dl className="grid grid-cols-[auto_minmax(0,1fr)] gap-x-6 gap-y-2 text-sm">
        <Fact label="Graph Source scope">{formatScope(observation.scope)}</Fact>
        <Fact label="Construction Run">
          {observation.run_id ? (
            <span className="flex items-center gap-1">
              <Link
                to={kgUrl(name, 'runs', observation.run_id)}
                className="truncate font-mono text-xs text-primary underline-offset-4 hover:underline"
              >
                {observation.run_id}
              </Link>
              <CopyButton value={observation.run_id} label="Copy run id" />
            </span>
          ) : (
            <span className="text-muted-foreground">None (on demand)</span>
          )}
        </Fact>
      </dl>
      {drift && <DriftDetails name={name} drift={drift} />}
    </article>
  )
}

function DriftDetails({ name, drift }: { name: string; drift: DriftEvent }) {
  const id = useId()
  return (
    <section aria-labelledby={id} className="space-y-3 border-t pt-4">
      <h4 id={id} className="text-sm font-semibold">
        Drift
      </h4>
      <dl className="grid grid-cols-[auto_minmax(0,1fr)] gap-x-6 gap-y-2 text-sm">
        <Fact label="Contract Alias">{drift.contract_alias}</Fact>
        <Fact label="Ontology Version">
          <Link
            to={kgUrl(name, 'versions', drift.ontology_version)}
            className="text-primary underline-offset-4 hover:underline"
          >
            v{drift.ontology_version}
          </Link>
        </Fact>
        <Fact label="Thresholds">{formatThresholds(drift.thresholds)}</Fact>
      </dl>
      <Table aria-label="Drift findings">
        <TableHeader>
          <TableRow>
            <TableHead>Kind</TableHead>
            <TableHead>Concept</TableHead>
            <TableHead>Detail</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {drift.findings.map((finding) => (
            <TableRow key={`${finding.kind}/${finding.subject_kind}/${finding.subject}`}>
              <TableCell>{humanize(finding.kind)}</TableCell>
              <TableCell>
                <span className="font-mono text-xs">{finding.subject}</span>{' '}
                <span className="text-muted-foreground">{humanize(finding.subject_kind)}</span>
              </TableCell>
              <TableCell className="text-muted-foreground">{finding.detail || '—'}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </section>
  )
}

function Fact({ label, children }: { label: string; children: ReactNode }) {
  return (
    <>
      <dt className="text-muted-foreground">{label}</dt>
      <dd className="min-w-0">{children}</dd>
    </>
  )
}

const percent = new Intl.NumberFormat(undefined, { style: 'percent', maximumFractionDigits: 1 })

/** `max count drop off · max count increase 50%` */
function formatThresholds(thresholds: DriftThresholds): string {
  return (['max_count_drop', 'max_count_increase'] as const)
    .map((key) => {
      const value = thresholds[key]
      return `${humanize(key)} ${value === null ? 'off' : percent.format(value)}`
    })
    .join(' · ')
}

/** `count_increase` → `count increase` */
function humanize(identifier: string): string {
  return identifier.replaceAll('_', ' ')
}
