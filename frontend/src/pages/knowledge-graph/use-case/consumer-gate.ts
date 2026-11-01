import type { MissingInput, RowCountFinding } from '@/api/consumer-gate-results'

const MINUS = '−'

const MISSING: Record<MissingInput, string> = {
  no_baseline_run: 'No baseline run to compare with',
  baseline_missing: 'No row count on the baseline run',
  baseline_error: 'The query failed on the baseline run',
  candidate_missing: 'No row count on the judged run',
  candidate_error: 'The query failed on the judged run',
}

const percent = (fraction: number, digits?: number) =>
  digits === undefined ? `${+(fraction * 100).toFixed(4)}%` : `${(fraction * 100).toFixed(digits)}%`

/**
 * What a failing question of a Consumer Gate lost, from its structured fields (never from
 * the human `reasons`): "5 → 2 rows (−60.0%, limit −10%)", or which input is missing.
 */
export function findingText(f: RowCountFinding): string {
  if (f.missing) return MISSING[f.missing]
  const change = f.change ?? 0
  const sign = change < 0 ? MINUS : '+'
  return `${f.before} → ${f.after} rows (${sign}${percent(Math.abs(change), 1)}, limit ${MINUS}${percent(f.limit)})`
}

/** A `row_count_drop` gate's `max_drop`, as the largest allowed drop. */
export function consumerGateLimit(maxDrop: number): string {
  return maxDrop === 0 ? 'no drop in rows' : `at most ${MINUS}${percent(maxDrop)} rows`
}
