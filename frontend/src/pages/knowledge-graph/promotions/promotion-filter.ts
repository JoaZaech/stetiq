import type { Promotion } from '@/api/aliases'
import { matchesSearch } from '@/lib/search'

export type PromotionGate = 'Passed' | 'Failed' | 'Not gated'
export const PROMOTION_GATES: readonly PromotionGate[] = ['Passed', 'Failed', 'Not gated']

/** How the Gate result column names a Promotion's Gate result. */
export function promotionGate(result: Promotion['gate_result']): PromotionGate {
  if (result === null) return 'Not gated'
  return result === 'passed' ? 'Passed' : 'Failed'
}

/** The Promotions the search (Alias, versions, actor) and the Gate filter (`''` for all) leave. */
export function filterPromotions(promotions: readonly Promotion[], query: string, gate: string): Promotion[] {
  return promotions.filter(
    (p) =>
      (gate === '' || promotionGate(p.gate_result) === gate) &&
      matchesSearch(query, [p.alias, p.from_version !== null ? `v${p.from_version}` : null, `v${p.to_version}`, p.actor]),
  )
}
