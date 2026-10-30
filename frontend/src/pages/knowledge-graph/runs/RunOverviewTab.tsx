import { useState } from 'react'
import { Link } from 'react-router'
import { type ConstructionRun, type RunObservation, useRunObservation } from '@/api/runs'
import { kgUrl } from '@/app/knowledge-graph-sections'
import { ErrorAlert } from '@/components/ErrorAlert'
import { Skeleton } from '@/components/ui/skeleton'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { formatDateTime, formatMetric } from '@/lib/format'
import { Fact, Panel } from '../versions/OverviewTab'
import { useConstructionRunTab } from './run-context'
import { formatDuration, runDurationMs } from './runs'

/** The run page's Overview tab: provenance, params, metrics and the ending Observation. */
export function RunOverviewTab() {
  const run = useConstructionRunTab()
  const [now] = useState(() => Date.now())
  return (
    <div className="grid gap-8 lg:grid-cols-[minmax(0,1fr)_minmax(0,2fr)]">
      <div className="space-y-8">
        <Panel title="Details">
          <dl className="grid grid-cols-[auto_minmax(0,1fr)] gap-x-6 gap-y-2 text-sm">
            <Fact label="Declared Ontology">
              <VersionLink kg={run.knowledge_graph} number={run.ontology_version} />
            </Fact>
            <Fact label="Candidate">
              {run.candidate_version === null ? (
                <span className="text-muted-foreground">None</span>
              ) : (
                <VersionLink kg={run.knowledge_graph} number={run.candidate_version} />
              )}
            </Fact>
            <Fact label="Started">{formatDateTime(run.started_at)}</Fact>
            <Fact label="Ended">
              {run.ended_at === null ? <span className="text-muted-foreground">Running</span> : formatDateTime(run.ended_at)}
            </Fact>
            <Fact label="Duration">{formatDuration(runDurationMs(run, now))}</Fact>
          </dl>
        </Panel>
        <Panel title="Observation">
          <EndingObservation run={run} />
        </Panel>
      </div>
      <div className="space-y-8">
        <Panel title="Params">
          <KeyValues
            label="Params"
            entries={Object.entries(run.params)}
            empty="No params logged."
            format={(v) => v}
          />
        </Panel>
        <Panel title="Metrics">
          <KeyValues
            label="Metrics"
            entries={Object.entries(run.metrics)}
            empty="No metrics logged."
            format={formatMetric}
          />
        </Panel>
      </div>
    </div>
  )
}

function VersionLink({ kg, number }: { kg: string; number: number }) {
  return (
    <Link to={kgUrl(kg, 'versions', number)} className="text-primary underline-offset-4 hover:underline">
      v{number}
    </Link>
  )
}

function KeyValues<T>({
  label,
  entries,
  empty,
  format,
}: {
  label: string
  entries: [string, T][]
  empty: string
  format: (value: T) => string
}) {
  if (entries.length === 0) return <p className="text-sm text-muted-foreground">{empty}</p>
  return (
    <Table aria-label={label}>
      <TableHeader>
        <TableRow>
          <TableHead>Name</TableHead>
          <TableHead>Value</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {[...entries]
          .sort(([a], [b]) => a.localeCompare(b))
          .map(([key, value]) => (
            <TableRow key={key}>
              <TableCell className="font-medium">{key}</TableCell>
              <TableCell className="tabular-nums">{format(value)}</TableCell>
            </TableRow>
          ))}
      </TableBody>
    </Table>
  )
}

/** The Observation of the Graph Source the run ended with: when, where, and its size. */
function EndingObservation({ run }: { run: ConstructionRun }) {
  const observation = useRunObservation(run.observation_id)
  if (run.observation_id === null) {
    return (
      <p className="text-sm text-muted-foreground">
        {run.status === 'running'
          ? 'The run observes its Graph Source when it ends.'
          : 'None: the run failed before its Graph Source was observed.'}
      </p>
    )
  }
  if (observation.isError) return <ErrorAlert error={observation.error} />
  if (observation.isPending) return <Skeleton className="h-20 w-full" />
  const { observed_at, schema } = observation.data
  return (
    <dl className="grid grid-cols-[auto_minmax(0,1fr)] gap-x-6 gap-y-2 text-sm">
      <Fact label="Observed">{formatDateTime(observed_at)}</Fact>
      <Fact label="Graph Source">{scopeLabel(observation.data.scope)}</Fact>
      <Fact label="Classes">{schema.node_types.length}</Fact>
      <Fact label="Relations">{schema.relationship_types.length}</Fact>
      <Fact label="Patterns">{schema.patterns.length}</Fact>
    </dl>
  )
}

/** e.g. `neo4j`, `neo4j · label Tenant · namespace acme` */
function scopeLabel({ database, label, namespace }: RunObservation['scope']) {
  return [database, label && `label ${label}`, namespace && `namespace ${namespace}`]
    .filter(Boolean)
    .join(' · ')
}
