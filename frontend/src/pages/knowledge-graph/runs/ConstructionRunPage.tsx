import { Suspense, useState } from 'react'
import { CircleX } from 'lucide-react'
import { Outlet, useParams } from 'react-router'
import { isNotFound } from '@/api/client'
import { type ConstructionRun, useRun } from '@/api/runs'
import { CopyButton } from '@/components/CopyButton'
import { ErrorAlert } from '@/components/ErrorAlert'
import { PageHeader } from '@/components/PageHeader'
import { RouteTabs, type RouteTab } from '@/components/RouteTabs'
import { RunStatusLabel } from '@/components/RunStatusLabel'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Skeleton } from '@/components/ui/skeleton'
import { formatDateTime } from '@/lib/format'
import { NotFoundPage } from '@/pages/NotFoundPage'
import { useKnowledgeGraphName } from '../params'
import { formatDuration, runDurationMs, runOutcome } from './runs'

/**
 * The run page's tabs. A tab is a child route of `runs/:runId` in `router.tsx` (`''` is
 * the index route); add it there and here. Tab pages read the run with
 * `useConstructionRunTab()`.
 */
const TABS: readonly RouteTab[] = [
  { label: 'Overview', to: '' },
  { label: 'Conformance', to: 'conformance' },
  { label: 'Evaluations', to: 'evaluations' },
]

/** `/kg/:name/runs/:runId`: the run id, status and duration, then the tabs. */
export function ConstructionRunPage() {
  const name = useKnowledgeGraphName()
  const runId = useParams().runId ?? ''
  const run = useRun(runId)

  // A run of another Knowledge Graph is not found here, as an unknown or unreadable one is.
  if ((run.isError && isNotFound(run.error)) || (run.data && run.data.knowledge_graph !== name)) {
    return (
      <NotFoundPage
        title="Construction Run not found"
        message={`Knowledge Graph “${name}” has no Construction Run ${runId}.`}
      />
    )
  }
  if (run.isError) return <ErrorAlert error={run.error} />
  if (run.isPending) return <Skeleton className="h-24 w-full" />
  return (
    <>
      <PageHeader
        title={run.data.id}
        description={<RunSummary run={run.data} />}
        actions={<CopyButton value={run.data.id} label="Copy run id" />}
      />
      <FailedRunAlert run={run.data} />
      <RouteTabs label="Construction Run" tabs={TABS} />
      <Suspense fallback={<Skeleton className="h-32 w-full" />}>
        <Outlet context={run.data} />
      </Suspense>
    </>
  )
}

function RunSummary({ run }: { run: ConstructionRun }) {
  const [now] = useState(() => Date.now())
  return (
    <span className="flex flex-wrap items-center gap-x-3 gap-y-1">
      <RunStatusLabel status={run.status} />
      <span>
        Started <time dateTime={run.started_at}>{formatDateTime(run.started_at)}</time>
      </span>
      <span>
        {run.status === 'running' ? 'Running for' : 'Took'} {formatDuration(runDurationMs(run, now))}
      </span>
    </span>
  )
}

/** Why a failed run failed, as far as stetiq knows. */
function FailedRunAlert({ run }: { run: ConstructionRun }) {
  const outcome = runOutcome(run)
  if (outcome !== 'failed' && outcome !== 'strict') return null
  return (
    <Alert variant="destructive" className="mb-6">
      <CircleX />
      <AlertTitle>This Construction Run failed</AlertTitle>
      <AlertDescription>
        {outcome === 'strict'
          ? 'It observed Concepts its Declared Ontology does not have, and the Knowledge Graph’s Evolution Mode is strict, so no Candidate was produced. The Conformance tab lists the Concepts observed but not declared.'
          : 'It failed before its Graph Source was observed: it was aborted, or the Observation failed. Nothing was observed and no Candidate was produced.'}
      </AlertDescription>
    </Alert>
  )
}
