import { describe, expect, it } from 'vitest'
import type { ConsumerGateResult } from '@/api/consumer-gate-results'
import { consumerGateLimit, consumerGateLine, findingText } from './consumer-gate'

describe('findingText', () => {
  it('states a row drop with its relative change and the limit', () => {
    expect(
      findingText({
        task: 'triage-breakdowns',
        competency_question: 'breakdown-technicians',
        limit: 0.1,
        before: 5,
        after: 2,
        change: -0.6,
      }),
    ).toBe('5 → 2 rows (−60.0%, limit −10%)')
  })

  it('says which input is missing instead of a change', () => {
    const base = { task: 't', competency_question: 'q', limit: 0.1 }
    expect(findingText({ ...base, missing: 'no_baseline_run', after: 3 })).toBe('No baseline run to compare with')
    expect(findingText({ ...base, missing: 'baseline_missing' })).toBe('No row count on the baseline run')
    expect(findingText({ ...base, missing: 'candidate_error', before: 4 })).toBe('The query failed on the judged run')
  })
})

describe('consumerGateLimit', () => {
  it('reads a max_drop as the largest allowed drop', () => {
    expect(consumerGateLimit(0.1)).toBe('at most −10% rows')
    expect(consumerGateLimit(0.125)).toBe('at most −12.5% rows')
    expect(consumerGateLimit(0)).toBe('no drop in rows')
  })
})

describe('consumerGateLine', () => {
  const gate = { name: 'rows-hold', check: 'row_count_drop', task: 'triage', max_drop: 0.1 }
  const result = (passed: boolean) => ({ passed }) as ConsumerGateResult

  it('is nothing for a Consumer that declares no Consumer Gate, verdict or not', () => {
    expect(consumerGateLine({ id: 'bot', name: 'Bot' }, undefined)).toBeNull()
    expect(consumerGateLine({ id: 'bot', name: 'Bot', consumer_gates: [] }, result(true))).toBeNull()
  })

  it('reads the latest verdict, and its absence as not evaluated yet', () => {
    const consumer = { id: 'bot', name: 'Bot', consumer_gates: [gate] }
    expect(consumerGateLine(consumer, result(true))).toEqual({ tone: 'success', label: 'Consumer Gate passed' })
    expect(consumerGateLine(consumer, result(false))).toEqual({ tone: 'failure', label: 'Consumer Gate failed' })
    expect(consumerGateLine(consumer, undefined)).toEqual({
      tone: 'neutral',
      label: 'Consumer Gate not evaluated yet',
    })
  })
})
