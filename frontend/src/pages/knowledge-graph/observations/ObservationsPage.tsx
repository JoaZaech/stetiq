import { useId, useMemo, useState, type ReactNode } from 'react'
import {
  Ban,
  ChevronDown,
  ChevronRight,
  CircleCheck,
  CircleMinus,
  CirclePlus,
  TrendingDown,
  TrendingUp,
} from 'lucide-react'
import { Link } from 'react-router'
import {
  type DriftEvent,
  type DriftFinding,
  type DriftThresholds,
  type Observation,
  useDriftEvents,
  useObservations,
} from '@/api/observations'
import { knowledgeGraphSection, kgUrl } from '@/app/knowledge-graph-sections'
import { ErrorAlert } from '@/components/ErrorAlert'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Planned } from '@/components/Planned'
import { StatusLabel } from '@/components/StatusLabel'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { conceptKindLabel } from '@/lib/concept-kind'
import { formatDateTime } from '@/lib/format'
import { KnowledgeGraphSectionPage } from '../KnowledgeGraphSectionPage'
import { useKnowledgeGraphName } from '../params'
import { shortRunId } from '../runs/runs'

const SECTION = knowledgeGraphSection('observations')

/**
 * `/kg/:name/observations`: a timeline of when the Graph Source was inspected, newest
 * first, one row each; only a row with Drift expands, to what it found against the
 * Contract Alias. Read-only: an Observation needs graph credentials, which never leave
 * the SDK process (`stetiq observe`).
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
      <ol aria-label="Observations" className="divide-y rounded-lg border">
        {newestFirst.map((observation) => (
          <ObservationRow
            key={observation.id}
            name={name}
            observation={observation}
            drift={driftByObservation.get(observation.id)}
          />
        ))}
      </ol>
    </div>
  )
}

/** `✓ No Drift · Oct 30, 2026, 14:05 · from run 1201b6ce`; a row with Drift expands to it. */
function ObservationRow({
  name,
  observation,
  drift,
}: {
  name: string
  observation: Observation
  drift: DriftEvent | undefined
}) {
  const id = useId()
  const [open, setOpen] = useState(false)
  const Chevron = open ? ChevronDown : ChevronRight
  return (
    <li className="px-3 py-2">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-sm">
        {drift ? (
          <Button
            variant="ghost"
            size="icon"
            className="-ml-1 size-7"
            aria-label="Drift details"
            aria-expanded={open}
            aria-controls={id}
            onClick={() => setOpen(!open)}
          >
            <Chevron aria-hidden className="size-4" />
          </Button>
        ) : (
          <span aria-hidden className="-ml-1 size-7" />
        )}
        <StatusLabel tone={drift ? 'warning' : 'success'} label={drift ? 'Drift' : 'No Drift'} />
        <time dateTime={observation.observed_at} className="text-muted-foreground">
          {formatDateTime(observation.observed_at)}
        </time>
        {observation.run_id ? (
          <span className="text-muted-foreground">
            from run{' '}
            <Link
              to={kgUrl(name, 'runs', observation.run_id)}
              className="font-mono text-xs text-primary underline-offset-4 hover:underline"
            >
              {shortRunId(observation.run_id)}
            </Link>
          </span>
        ) : (
          <span className="text-muted-foreground">on demand</span>
        )}
      </div>
      {drift && (
        <div id={id} hidden={!open} className="pt-3 pb-1 pl-10">
          <DriftDetails name={name} drift={drift} />
        </div>
      )}
    </li>
  )
}

function DriftDetails({ name, drift }: { name: string; drift: DriftEvent }) {
  return (
    <section aria-label="Drift" className="space-y-3">
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
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2 text-xs">
        <Planned
          label="Pending Migration"
          section="pending-migration-and-adoption"
          tooltip="Drift that the Ontology Diff since the last version the Graph Source conformed to explains will be shown as a Pending Migration, raising no alert until a grace period ends."
        >
          Pending Migration
        </Planned>
        {drift.findings.some((f) => ADOPTABLE.has(f.kind)) && (
          <Planned
            label="Adoption"
            section="pending-migration-and-adoption"
            tooltip="Selected undeclared Concepts will be added to a new Candidate, and selected vanished ones deprecated."
          >
            <Button size="sm" variant="outline" disabled>
              Adopt into a Candidate
            </Button>
          </Planned>
        )}
      </div>
      <ul aria-label="Drift findings" className="space-y-1.5 text-sm">
        {drift.findings.map((finding) => (
          <Finding
            key={`${finding.kind}/${finding.subject_kind}/${finding.subject}/${finding.value ?? ''}`}
            finding={finding}
          />
        ))}
      </ul>
    </section>
  )
}

/** Each Drift finding kind's icon, and what it means when the finding has no detail of its own. */
const FINDING_KIND = {
  undeclared: { Icon: CirclePlus, label: 'observed but not declared' },
  vanished: { Icon: CircleMinus, label: 'no longer observed' },
  undeclared_value: { Icon: Ban, label: 'value outside the Vocabulary' },
  count_drop: { Icon: TrendingDown, label: 'count dropped' },
  count_increase: { Icon: TrendingUp, label: 'count rose' },
} as const satisfies Record<DriftFinding['kind'], { Icon: unknown; label: string }>

/** `⊕ Refund Class — observed but not declared`, `↗ Ticket Class — count rose from 1 to 4 (+300%)` */
function Finding({ finding }: { finding: DriftFinding }) {
  const { Icon, label } = FINDING_KIND[finding.kind]
  return (
    <li className="flex items-start gap-2">
      <Icon aria-hidden className="mt-0.5 size-4 shrink-0 text-warning" />
      <span className="min-w-0">
        {finding.detail && <span className="sr-only">{label}: </span>}
        <span className="font-mono text-xs">{finding.subject}</span>{' '}
        <span className="text-muted-foreground">{conceptKindLabel(finding.subject_kind)}</span>
        <span className="text-muted-foreground"> — {finding.detail || label}</span>
      </span>
    </li>
  )
}

/** Drift finding kinds an Adoption could take into a Candidate: undeclared and vanished Concepts. */
const ADOPTABLE = new Set(['undeclared', 'vanished'])

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

/** `max_count_drop` → `max count drop` */
function humanize(identifier: string): string {
  return identifier.replaceAll('_', ' ')
}
