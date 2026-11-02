import { type GateResult, latestGateResult, useGateResults } from '@/api/gate-results'
import { Disclosure } from '@/components/Disclosure'
import { ErrorAlert } from '@/components/ErrorAlert'
import { StatusLabel } from '@/components/StatusLabel'
import { Skeleton } from '@/components/ui/skeleton'
import { formatDateTime, formatRelativeTime } from '@/lib/format'
import { gateResultSummary } from './gate-summary'

/**
 * An Ontology Version's latest Gate result: "2 of 9 Gates failed" or "All 9 Gates
 * passed", each failed Gate with its reasons, and the passed ones folded. "Not gated"
 * when no Gate was evaluated on it. Shown on the Overview tab and in the Promote dialog.
 */
export function LatestGateResult({ name, number }: { name: string; number: number }) {
  const results = useGateResults(name)
  if (results.isPending) return <Skeleton className="h-6 w-32" />
  if (results.isError) return <ErrorAlert error={results.error} />
  const latest = latestGateResult(results.data, 'ontology_version', String(number))
  if (!latest) {
    return (
      <p className="flex flex-wrap items-center gap-x-2 gap-y-1 text-sm">
        <StatusLabel tone="neutral" label="Not gated" />
        <span className="text-muted-foreground">No Gates have been evaluated on this version.</span>
      </p>
    )
  }
  return <GateOutcomes result={latest} />
}

function GateOutcomes({ result }: { result: GateResult }) {
  const failed = result.outcomes.filter((o) => !o.passed)
  const passed = result.outcomes.filter((o) => o.passed)
  return (
    <div className="space-y-2 text-sm">
      <p className="flex flex-wrap items-center gap-x-2 gap-y-1">
        <span className="font-medium">
          <StatusLabel tone={result.passed ? 'success' : 'failure'} label={gateResultSummary(result)} />
        </span>
        <span className="text-muted-foreground">
          evaluated{' '}
          <time dateTime={result.evaluated_at} title={formatDateTime(result.evaluated_at)}>
            {formatRelativeTime(result.evaluated_at)}
          </time>
        </span>
      </p>
      {failed.length > 0 && (
        <ul aria-label="Failed Gates" className="space-y-1.5">
          {failed.map((outcome) => (
            <li key={outcome.gate.name}>
              <StatusLabel tone="failure" label={outcome.gate.name} />
              {outcome.reasons.length > 0 && (
                <ul className="mt-0.5 space-y-0.5 pl-5.5 text-muted-foreground">
                  {outcome.reasons.map((reason) => (
                    <li key={reason}>{reason}</li>
                  ))}
                </ul>
              )}
            </li>
          ))}
        </ul>
      )}
      {passed.length > 0 && (
        <Disclosure label={`${passed.length} passed`}>
          <ul aria-label="Passed Gates" className="space-y-1">
            {passed.map((outcome) => (
              <li key={outcome.gate.name}>
                <StatusLabel tone="success" label={outcome.gate.name} />
              </li>
            ))}
          </ul>
        </Disclosure>
      )}
    </div>
  )
}
