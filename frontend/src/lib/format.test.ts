import { describe, expect, it } from 'vitest'
import { formatFraction, formatPercent, formatPoints, formatRelativeTime } from './format'

describe('formatRelativeTime', () => {
  const now = new Date('2026-11-01T12:00:00Z')

  it('names the largest whole unit since the timestamp', () => {
    expect(formatRelativeTime('2026-11-01T11:59:30Z', now)).toBe('just now')
    expect(formatRelativeTime('2026-11-01T11:55:00Z', now)).toMatch(/5 minutes ago/)
    expect(formatRelativeTime('2026-11-01T09:00:00Z', now)).toMatch(/3 hours ago/)
    expect(formatRelativeTime('2026-10-30T12:00:00Z', now)).toMatch(/2 days ago/)
  })
})

describe('formatPercent', () => {
  it('shows a ratio as a percentage, to one decimal at most', () => {
    expect(formatPercent(0.7097)).toBe('71%')
    expect(formatPercent(0.995)).toBe('99.5%')
    expect(formatPercent(1)).toBe('100%')
    expect(formatPercent(0)).toBe('0%')
  })
})

describe('formatFraction', () => {
  it('shows a count out of its total', () => {
    expect(formatFraction(5, 6)).toBe('5 / 6')
    expect(formatFraction(0, 0)).toBe('0 / 0')
  })
})

describe('formatPoints', () => {
  it('shows a difference of ratios in percentage points, singular only for exactly 1', () => {
    expect(formatPoints(0.025)).toBe('2.5 pts')
    expect(formatPoints(0.01)).toBe('1 pt')
    expect(formatPoints(0.0100000001)).toBe('1 pt')
    expect(formatPoints(0.011)).toBe('1.1 pts')
    expect(formatPoints(0.05)).toBe('5 pts')
    expect(formatPoints(0)).toBe('0 pts')
  })

  it('signs a change on request, with a true minus', () => {
    expect(formatPoints(0.025, { signed: true })).toBe('+2.5 pts')
    expect(formatPoints(-0.1, { signed: true })).toBe('−10 pts')
    expect(formatPoints(0.01, { signed: true })).toBe('+1 pt')
    expect(formatPoints(-0.01, { signed: true })).toBe('−1 pt')
  })
})
