import { latestGateResult, useGateResults } from '@/api/gate-results'
import { ErrorAlert } from '@/components/ErrorAlert'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import { formatCount, formatDateTime } from '@/lib/format'

/**
 * An Ontology Version's latest Gate result: Passed, Failed or None, with when it was
 * evaluated and which Gates failed. Shown on the Overview tab and in the Promote dialog.
 */
export function LatestGateResult({ name, number }: { name: string; number: number }) {
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
        {formatDateTime(latest.evaluated_at)} · {formatCount(latest.outcomes.length, 'Gate')}
        {failed.length > 0 && `, failed: ${failed.join(', ')}`}
      </span>
    </p>
  )
}
