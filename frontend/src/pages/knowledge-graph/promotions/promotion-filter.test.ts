import { describe, expect, it } from 'vitest'
import type { Promotion } from '@/api/aliases'
import { filterPromotions, promotionGate } from './promotion-filter'

const promotion = (p: Partial<Promotion>): Promotion => ({
  knowledge_graph: 'support',
  alias: 'production',
  from_version: 1,
  to_version: 2,
  actor: 'ada',
  promoted_at: '2026-11-02T10:00:00Z',
  gate_result: 'passed',
  ...p,
})

describe('promotionGate', () => {
  it('names each Gate result', () => {
    expect([promotionGate('passed'), promotionGate('failed'), promotionGate(null)]).toEqual([
      'Passed',
      'Failed',
      'Not gated',
    ])
  })
})

describe('filterPromotions', () => {
  const promotions = [
    promotion({}),
    promotion({ alias: 'staging', from_version: null, to_version: 3, actor: 'bob', gate_result: null }),
  ]

  it('filters by Gate result', () => {
    expect(filterPromotions(promotions, '', 'Not gated').map((p) => p.alias)).toEqual(['staging'])
  })

  it('searches the Alias, versions and actor', () => {
    expect(filterPromotions(promotions, 'v3', '').map((p) => p.alias)).toEqual(['staging'])
    expect(filterPromotions(promotions, 'ada', '').map((p) => p.alias)).toEqual(['production'])
  })
})
