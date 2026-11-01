import { describe, expect, it } from 'vitest'
import { gateResultSummary } from './gate-summary'

const outcome = (passed: boolean) => ({ gate: { name: 'g' }, passed, reasons: [] })

describe('gateResultSummary', () => {
  it('counts the failed Gates out of all of them', () => {
    expect(gateResultSummary({ outcomes: [outcome(false), outcome(true), outcome(false)] })).toBe(
      '2 of 3 Gates failed',
    )
    expect(gateResultSummary({ outcomes: [outcome(false)] })).toBe('1 of 1 Gate failed')
  })

  it('says all passed when none failed', () => {
    expect(gateResultSummary({ outcomes: [outcome(true), outcome(true)] })).toBe('All 2 Gates passed')
    expect(gateResultSummary({ outcomes: [outcome(true)] })).toBe('The 1 Gate passed')
  })
})
