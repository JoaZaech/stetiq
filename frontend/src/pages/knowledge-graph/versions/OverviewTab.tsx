import { useId, type ReactNode } from 'react'
import { Link } from 'react-router'
import { useVersionEvaluations } from '@/api/ontology-versions'
import { useRuns } from '@/api/runs'
import { kgUrl } from '@/app/knowledge-graph-sections'
import { CopyButton } from '@/components/CopyButton'
import { Disclosure } from '@/components/Disclosure'
import { Planned } from '@/components/Planned'
import { ErrorAlert } from '@/components/ErrorAlert'
import { Skeleton } from '@/components/ui/skeleton'
import { formatDateTime } from '@/lib/format'
import { useKnowledgeGraphName } from '../params'
import { EvaluatorResults } from './EvaluatorResults'
import { LatestGateResult } from './LatestGateResult'
import { useOntologyVersionTab } from './version-context'

/**
 * The version page's Overview tab: its latest Gate result first (with the planned Gate
 * on Consumer impact), then one card per Evaluator with every metric behind a toggle,
 * then its Details, folded.
 */
export function OverviewTab() {
  const name = useKnowledgeGraphName()
  const version = useOntologyVersionTab()
  return (
    <div className="space-y-8">
      <Panel title="Gate result">
        <LatestGateResult name={name} number={version.number} />
        <Planned
          label="Gate on Consumer impact"
          section="consumer-impact-and-gates-over-it"
          tooltip="A Gate that fails when a change in this version would affect a Consumer's Tasks."
          className="text-sm"
        >
          Gate on Consumer impact
        </Planned>
      </Panel>
      <Panel title="Evaluator results">
        <VersionEvaluatorResults name={name} number={version.number} />
      </Panel>
      <Disclosure label="Details" heading>
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
      </Disclosure>
    </div>
  )
}

export function Panel({ title, children }: { title: string; children: ReactNode }) {
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

export function Fact({ label, children }: { label: string; children: ReactNode }) {
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

function VersionEvaluatorResults({ name, number }: { name: string; number: number }) {
  const results = useVersionEvaluations(name, number)
  if (results.isPending) return <Skeleton className="h-32 w-full" />
  if (results.isError) return <ErrorAlert error={results.error} />
  return <EvaluatorResults results={results.data} empty="No Evaluator results for this version." />
}
