import { useId, type ReactNode } from 'react'
import { Link } from 'react-router'
import { latestGateResult, useGateResults } from '@/api/gate-results'
import { useVersionEvaluations, type EvaluationResult } from '@/api/ontology-versions'
import { useRuns } from '@/api/runs'
import { kgUrl } from '@/app/knowledge-graph-sections'
import { CopyButton } from '@/components/CopyButton'
import { ErrorAlert } from '@/components/ErrorAlert'
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
import { formatDateTime, formatMetric } from '@/lib/format'
import { useKnowledgeGraphName } from '../params'
import { useOntologyVersionTab } from './version-context'

/** The version page's Overview tab: metadata, Evaluator results and latest Gate result. */
export function OverviewTab() {
  const name = useKnowledgeGraphName()
  const version = useOntologyVersionTab()
  return (
    <div className="grid gap-8 lg:grid-cols-[minmax(0,1fr)_minmax(0,2fr)]">
      <Panel title="Details">
        <dl className="grid grid-cols-[auto_minmax(0,1fr)] gap-x-6 gap-y-2 text-sm">
          <Fact label="Number">{version.number}</Fact>
          <Fact label="Origin">{version.origin}</Fact>
          <Fact label="Content hash">
            <span className="flex items-center gap-1">
              <code className="truncate font-mono text-xs" title={version.content_hash}>
                {version.content_hash}
              </code>
              <CopyButton value={version.content_hash} label="Copy content hash" />
            </span>
          </Fact>
          <Fact label="Created">{formatDateTime(version.created_at)}</Fact>
          {version.origin === 'run' && (
            <Fact label="Construction Run">
              <SourceRun name={name} number={version.number} />
            </Fact>
          )}
        </dl>
      </Panel>
      <div className="space-y-8">
        <Panel title="Evaluator results">
          <EvaluatorResults name={name} number={version.number} />
        </Panel>
        <Panel title="Latest Gate result">
          <LatestGateResult name={name} number={version.number} />
        </Panel>
      </div>
    </div>
  )
}

function Panel({ title, children }: { title: string; children: ReactNode }) {
  const id = useId()
  return (
    <section aria-labelledby={id} className="min-w-0 space-y-3">
      <h2 id={id} className="text-sm font-semibold">
        {title}
      </h2>
      {children}
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

/** The Construction Run that produced a run-originated version (its Candidate). */
function SourceRun({ name, number }: { name: string; number: number }) {
  const runs = useRuns(name)
  if (runs.isPending) return <Skeleton className="h-4 w-48" />
  if (runs.isError) return <span className="text-destructive">{runs.error.message}</span>
  const run = runs.data.find((r) => r.candidate_version === number)
  if (!run) return <span className="text-muted-foreground">Unknown</span>
  return (
    <span className="flex items-center gap-1">
      <Link
        to={kgUrl(name, 'runs', run.id)}
        className="truncate font-mono text-xs text-primary underline-offset-4 hover:underline"
      >
        {run.id}
      </Link>
      <CopyButton value={run.id} label="Copy run id" />
    </span>
  )
}

/** One row per metric, as `evaluator · metric · value · Use Case Version`. */
function metricRows(results: readonly EvaluationResult[]) {
  return [...results]
    .sort((a, b) => a.evaluator.localeCompare(b.evaluator))
    .flatMap((result) => {
      const params = Object.entries(result.parameters)
      const evaluator =
        params.length === 0
          ? result.evaluator
          : `${result.evaluator} (${params.map(([k, v]) => `${k}=${JSON.stringify(v)}`).join(', ')})`
      return Object.entries(result.metrics)
        .sort(([a], [b]) => a.localeCompare(b))
        .map(([metric, value]) => ({
          key: `${evaluator}/${metric}`,
          evaluator,
          metric,
          value,
          useCaseVersion: result.use_case_version,
        }))
    })
}

function EvaluatorResults({ name, number }: { name: string; number: number }) {
  const results = useVersionEvaluations(name, number)
  if (results.isPending) return <Skeleton className="h-32 w-full" />
  if (results.isError) return <ErrorAlert error={results.error} />
  const rows = metricRows(results.data)
  if (rows.length === 0) {
    return <p className="text-sm text-muted-foreground">No Evaluator results for this version.</p>
  }
  return (
    <Table aria-label="Evaluator results">
      <TableHeader>
        <TableRow>
          <TableHead>Evaluator</TableHead>
          <TableHead>Metric</TableHead>
          <TableHead className="text-right">Value</TableHead>
          <TableHead className="text-right">Use Case Version</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {rows.map((row) => (
          <TableRow key={row.key}>
            <TableCell>{row.evaluator}</TableCell>
            <TableCell>{row.metric}</TableCell>
            <TableCell className="text-right tabular-nums">{formatMetric(row.value)}</TableCell>
            <TableCell className="text-right tabular-nums">
              {row.useCaseVersion ?? <span className="text-muted-foreground">—</span>}
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  )
}

function LatestGateResult({ name, number }: { name: string; number: number }) {
  const results = useGateResults(name)
  if (results.isPending) return <Skeleton className="h-6 w-32" />
  if (results.isError) return <ErrorAlert error={results.error} />
  const latest = latestGateResult(results.data, 'ontology_version', String(number))
  if (!latest) {
    return (
      <p className="flex items-center gap-2 text-sm">
        <Badge variant="outline">None</Badge>
        <span className="text-muted-foreground">No Gates have been evaluated on this version.</span>
      </p>
    )
  }
  const failed = latest.outcomes.filter((o) => !o.passed).map((o) => o.gate.name)
  return (
    <p className="flex flex-wrap items-center gap-2 text-sm">
      <Badge variant={latest.passed ? 'default' : 'destructive'}>{latest.passed ? 'Passed' : 'Failed'}</Badge>
      <span className="text-muted-foreground">
        {formatDateTime(latest.evaluated_at)} · {latest.outcomes.length} Gate
        {latest.outcomes.length === 1 ? '' : 's'}
        {failed.length > 0 && `, failed: ${failed.join(', ')}`}
      </span>
    </p>
  )
}
