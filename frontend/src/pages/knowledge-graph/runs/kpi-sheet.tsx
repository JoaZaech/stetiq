import { type ReactNode, useId } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router'
import { gatePreviewsQuery } from '@/api/gate-previews'
import { gateResultsQuery } from '@/api/gate-results'
import { runEvaluationsQuery, runQuery } from '@/api/runs'
import { kgUrl } from '@/app/knowledge-graph-sections'
import { ErrorAlert } from '@/components/ErrorAlert'
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from '@/components/ui/sheet'
import { Skeleton } from '@/components/ui/skeleton'
import { formatMetric } from '@/lib/format'
import { type Kpi, type KpiDrillDown, kpiDrillDown, kpiName, runGating } from './compare'
import { NoResult, PassFail, VerdictBadge } from './gate-verdicts'

/** The run and KPI the drill-down is open for. */
export interface KpiSelection {
  runId: string
  kpi: Kpi
}

const TAB_LABELS: Record<KpiDrillDown['tab'], string> = {
  overview: 'Overview',
  evaluations: 'Evaluations',
  conformance: 'Conformance',
}

/**
 * The KPI drill-down: a side sheet about one run's KPI (its value, verdict with origin and
 * Gate reasons, and an Evaluator KPI's detail items about its metric), linking to the run
 * page tab it comes from. Open while `selection` is set; reads the run, its Evaluator
 * results, the Gate results and the Gate Previews (cached when the page already has them).
 */
export function KpiSheet({
  knowledgeGraph,
  selection,
  onClose,
}: {
  knowledgeGraph: string
  selection: KpiSelection | null
  onClose: () => void
}) {
  return (
    <Sheet open={selection !== null} onOpenChange={(open) => !open && onClose()}>
      <SheetContent className="overflow-y-auto sm:max-w-md">
        {selection && (
          <>
            <SheetHeader>
              <SheetTitle className="break-all">{kpiName(selection.kpi)}</SheetTitle>
              <SheetDescription className="break-all">Construction Run {selection.runId}</SheetDescription>
            </SheetHeader>
            <div className="space-y-6 px-4 pb-4">
              <DrillDown knowledgeGraph={knowledgeGraph} {...selection} />
            </div>
          </>
        )}
      </SheetContent>
    </Sheet>
  )
}

function DrillDown({ knowledgeGraph, runId, kpi }: { knowledgeGraph: string } & KpiSelection) {
  const run = useQuery(runQuery(runId))
  const evaluations = useQuery(runEvaluationsQuery(knowledgeGraph, runId))
  const gateResults = useQuery(gateResultsQuery(knowledgeGraph))
  const gatePreviews = useQuery(gatePreviewsQuery(knowledgeGraph))
  const failed = [run, evaluations, gateResults, gatePreviews].find((q) => q.isError)
  if (failed) return <ErrorAlert error={failed.error} />
  if (!run.data || !evaluations.data || !gateResults.data || !gatePreviews.data) {
    return <Skeleton className="h-32 w-full" />
  }
  const drill = kpiDrillDown(kpi, run.data, evaluations.data, runGating(runId, gateResults.data, gatePreviews.data))
  const { verdict } = drill
  return (
    <>
      <dl className="space-y-1">
        <dt className="text-xs text-muted-foreground">Value</dt>
        <dd className="text-2xl font-semibold tabular-nums">
          {drill.value === null ? <NoResult /> : formatMetric(drill.value)}
        </dd>
      </dl>
      <Section title="Verdict">
        {verdict.verdict === 'ungated' ? (
          <p className="text-muted-foreground">No Gate covers this KPI.</p>
        ) : (
          <>
            <p className="flex items-center gap-2">
              <VerdictBadge verdict={verdict} />
            </p>
            <p className="text-muted-foreground">
              {verdict.origin === 'preview'
                ? 'This verdict is judged against current Gates (a Gate Preview), not recorded by CI.'
                : 'This verdict is from the recorded Gate result about this run.'}
            </p>
            {verdict.outcomes.map((outcome) => (
              <div key={outcome.gate.name} className="space-y-1">
                <p className="flex items-center gap-2 font-medium">
                  {outcome.gate.name}
                  <PassFail passed={outcome.passed} origin={verdict.origin} />
                </p>
                <ul aria-label={`${outcome.gate.name} reasons`} className="list-disc space-y-0.5 pl-5 font-mono text-xs">
                  {outcome.reasons.map((reason, i) => (
                    <li key={i}>{reason}</li>
                  ))}
                </ul>
              </div>
            ))}
          </>
        )}
      </Section>
      {kpi.kind === 'evaluator' && (
        <Section title="Detail items">
          {drill.details.length === 0 ? (
            <p className="text-muted-foreground">No detail items about this metric.</p>
          ) : (
            <ul aria-label="Detail items" className="space-y-1">
              {drill.details.map((detail, i) => (
                <li key={i}>
                  <span className="font-mono text-xs">{detail.item}</span>
                  {detail.message && <span className="text-muted-foreground"> {detail.message}</span>}
                </li>
              ))}
            </ul>
          )}
        </Section>
      )}
      <Link
        to={kgUrl(knowledgeGraph, 'runs', runId, ...(drill.tab === 'overview' ? [] : [drill.tab]))}
        className="inline-block text-primary underline-offset-4 hover:underline"
      >
        Open the run’s {TAB_LABELS[drill.tab]} tab
      </Link>
    </>
  )
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  const id = useId()
  return (
    <section aria-labelledby={id} className="space-y-2">
      <h3 id={id} className="text-sm font-semibold">
        {title}
      </h3>
      {children}
    </section>
  )
}
