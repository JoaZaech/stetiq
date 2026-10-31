import { Link } from 'react-router'
import type { GatePreview } from '@/api/gate-previews'
import { kgUrl } from '@/app/knowledge-graph-sections'
import { StatusLabel } from '@/components/StatusLabel'
import { formatDateTime } from '@/lib/format'
import type { KpiSummary, Verdict, VerdictOrigin } from './compare'
import { shortRunId } from './runs'

/** How a Gate Preview's verdicts are labelled: they are not what CI recorded. */
const PREVIEW_TITLE = 'judged against current Gates'

/** Whether a verdict was recorded by CI or previewed, in text. */
export function VerdictOriginLabel({ origin }: { origin: VerdictOrigin }) {
  return (
    <span
      className="text-xs text-muted-foreground"
      title={origin === 'preview' ? PREVIEW_TITLE : 'recorded Gate result'}
    >
      {origin}
    </span>
  )
}

/** A pass/fail verdict in text and colour, with its origin. */
export function PassFail({ passed, origin }: { passed: boolean; origin: VerdictOrigin }) {
  return (
    <span className="inline-flex items-center gap-1.5">
      <StatusLabel tone={passed ? 'success' : 'failure'} label={passed ? 'pass' : 'fail'} />
      <VerdictOriginLabel origin={origin} />
    </span>
  )
}

/** A KPI cell's verdict next to its value; nothing for an ungated KPI. */
export function VerdictBadge({ verdict }: { verdict: Verdict }) {
  if (verdict.verdict === 'ungated') return null
  if (verdict.verdict === 'no-result') return <VerdictOriginLabel origin={verdict.origin} />
  return <PassFail passed={verdict.verdict === 'pass'} origin={verdict.origin} />
}

/** "No result": a gated KPI the run has no value for, which is not a bad score. */
export function NoResult() {
  return <span className="text-muted-foreground">no result</span>
}

/** A gated KPI's pass percentage and pass/fail bar across the compared runs. */
export function KpiSummaryBar({ summary }: { summary: KpiSummary }) {
  const parts = [
    `${summary.pass} of ${summary.gated} runs pass`,
    summary.fail > 0 ? `${summary.fail} fail` : null,
    summary.noResult > 0 ? `${summary.noResult} no result` : null,
  ].filter((p) => p !== null)
  const segments = [
    { count: summary.pass, className: 'bg-success' },
    { count: summary.fail, className: 'bg-destructive' },
    { count: summary.noResult, className: 'bg-muted-foreground/40' },
  ]
  return (
    <span className="mt-1 flex items-center gap-2 text-xs font-normal text-muted-foreground">
      <span className="tabular-nums">{Math.round((summary.pass / summary.gated) * 100)}% pass</span>
      <span role="img" aria-label={parts.join(', ')} className="flex h-1.5 w-20 overflow-hidden rounded-full bg-muted">
        {segments.map(
          (s, i) => s.count > 0 && <span key={i} className={s.className} style={{ flexGrow: s.count }} />,
        )}
      </span>
    </span>
  )
}

/** Names the Gate result whose Gate definitions the previews used. */
export function GatePreviewNote({ knowledgeGraph, source }: { knowledgeGraph: string; source: GatePreview['source'] }) {
  const subject =
    source.subject_kind === 'construction_run' ? (
      <>
        Construction Run{' '}
        <Link
          to={kgUrl(knowledgeGraph, 'runs', source.subject_id)}
          title={source.subject_id}
          className="font-mono text-primary underline-offset-4 hover:underline"
        >
          {shortRunId(source.subject_id)}
        </Link>
      </>
    ) : (
      <>Ontology Version v{source.subject_id}</>
    )
  return (
    <p role="note" aria-label="Gate Preview source" className="text-sm text-muted-foreground">
      Verdicts marked <em>preview</em> are {PREVIEW_TITLE}: the Gates of the Gate result about {subject}, evaluated{' '}
      <time dateTime={source.evaluated_at}>{formatDateTime(source.evaluated_at)}</time>. Verdicts marked{' '}
      <em>recorded</em> are Gate results CI recorded about that run.
    </p>
  )
}

/** Shown when the Knowledge Graph was never gated: how to turn verdicts on. */
export function NeverGatedHint() {
  return (
    <p role="note" aria-label="Gates" className="text-sm text-muted-foreground">
      No Gate verdicts yet: write Gates in <code>stetiq.yaml</code> and run <code>stetiq gate</code> to judge runs
      against them.
    </p>
  )
}
