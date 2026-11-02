import { describe, expect, it } from 'vitest'
import { evaluationKpis, NOT_APPLICABLE } from './evaluation-kpis'

describe('evaluationKpis', () => {
  it('always gives the same four tiles in the same order', () => {
    const kpis = evaluationKpis({})
    expect(kpis.map((k) => k.label)).toEqual(['Conformance', 'CQ coverage', 'Gates', 'Drift'])
    expect(kpis.every((k) => k.value === NOT_APPLICABLE && k.tone === undefined)).toBe(true)
  })

  it('formats and tones each value', () => {
    const [conformance, coverage, gates, drift] = evaluationKpis(
      { conformance: 0.8889, coverage: { count: 2, total: 9 }, gates: { count: 9, total: 9 }, drift: 5 },
      { drift: '/kg/x/observations' },
    )
    expect(conformance).toMatchObject({ value: '88.9%', tone: 'warning' })
    expect(coverage).toMatchObject({ value: '2/9', tone: 'warning' })
    expect(gates).toMatchObject({ value: '9/9', tone: 'success' })
    expect(drift).toMatchObject({ value: '5', tone: 'warning', hint: 'findings', to: '/kg/x/observations' })
  })

  it('reads none answerable as a failure and no Drift as a success', () => {
    const [, coverage, gates, drift] = evaluationKpis({
      coverage: { count: 0, total: 3 },
      gates: { count: 0, total: 0 },
      drift: 0,
    })
    expect(coverage.tone).toBe('failure')
    expect(gates.value).toBe(NOT_APPLICABLE)
    expect(drift.tone).toBe('success')
  })
})
