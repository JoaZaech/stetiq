import { Suspense, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { CircleX } from 'lucide-react'
import { Link, Outlet, useParams } from 'react-router'
import { isNotFound } from '@/api/client'
import { gateResultsQuery } from '@/api/gate-results'
import { useDriftEvents } from '@/api/observations'
import { type ConstructionRun, useRun, useRunEvaluations } from '@/api/runs'
import { kgUrl } from '@/app/knowledge-graph-sections'
import { ErrorAlert } from '@/components/ErrorAlert'
import { KpiTiles } from '@/components/KpiTiles'
import { PageHeader } from '@/components/PageHeader'
import { RouteTabs, type RouteTab } from '@/components/RouteTabs'
import { RunStatusLabel } from '@/components/RunStatusLabel'
import { Alert, AlertTitle } from '@/components/ui/alert'
import { Skeleton } from '@/components/ui/skeleton'
import { formatDateTime } from '@/lib/format'
import { NotFoundPage } from '@/pages/NotFoundPage'
import { evaluationKpis } from '../evaluation/evaluation-kpis'
import { useKnowledgeGraphName } from '../params'
import { FINDING_PARAM } from './run-context'
import { formatDuration, runDurationMs, runEvaluationInputs, runFailure, shortRunId } from './runs'

/**
 * The run page's tabs. A tab is a child route of `runs/:runId` in `router.tsx` (`''` is
 * the index route); add it there and here. Tab pages read the run with
 * `useConstructionRunTab()`.
 */
const TABS: readonly RouteTab[] = [
  { label: 'Overview', to: '' },
  { label: 'Evaluation', to: 'evaluation' },
]

/**
 * `/kg/:name/runs/:runId`: the detail layout every evaluated thing shares: the short run
 * id, one metadata line (status, start, duration), a one-line banner if it failed, the
 * four evaluation KPI tiles, then the tabs. The full id and params are in the Overview tab.
 */
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
      <PageHeader title={shortRunId(run.data.id)} description={<RunSummary run={run.data} />} />
      <FailedRunAlert run={run.data} />
      <RunKpis run={run.data} />
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

/** Why a failed run failed, in one line, linking to the findings that show it. */
function FailedRunAlert({ run }: { run: ConstructionRun }) {
  const failure = runFailure(run)
  if (failure === null) return null
  const findings =
    failure.finding &&
    `${kgUrl(run.knowledge_graph, 'runs', run.id, 'evaluation')}?${new URLSearchParams({ [FINDING_PARAM]: failure.finding })}`
  return (
    <Alert variant="destructive" className="mb-4">
      <CircleX />
      <AlertTitle className="flex flex-wrap items-center gap-x-2">
        {failure.text}
        {findings && (
          <Link to={findings} className="font-normal underline underline-offset-4">
            Show
          </Link>
        )}
      </AlertTitle>
    </Alert>
  )
}

/**
 * The four evaluation KPIs (Conformance, CQ coverage, Gates, Drift) of the run, as on
 * every evaluated page; each shows `—` until its data loads or where it does not apply.
 */
function RunKpis({ run }: { run: ConstructionRun }) {
  const evaluations = useRunEvaluations(run.knowledge_graph, run.id)
  const gateResults = useQuery(gateResultsQuery(run.knowledge_graph))
  const driftEvents = useDriftEvents(run.knowledge_graph)
  const evaluation = kgUrl(run.knowledge_graph, 'runs', run.id, 'evaluation')
  const tiles = evaluationKpis(runEvaluationInputs(run, evaluations.data, gateResults.data, driftEvents.data), {
    conformance: evaluation,
    coverage: evaluation,
    drift: kgUrl(run.knowledge_graph, 'observations'),
  })
  return <KpiTiles tiles={tiles} label="Evaluation" className="mb-6" />
}
