import type { GateResult } from '@/api/gate-results'

/** A Gate result's headline: "2 of 9 Gates failed", or "All 9 Gates passed". */
export function gateResultSummary(result: Pick<GateResult, 'outcomes'>): string {
  const total = result.outcomes.length
  const failed = result.outcomes.filter((o) => !o.passed).length
  const gates = total === 1 ? 'Gate' : 'Gates'
  if (failed > 0) return `${failed} of ${total} ${gates} failed`
  return total === 1 ? 'The 1 Gate passed' : `All ${total} Gates passed`
}
