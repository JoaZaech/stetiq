import { describe, expect, it } from 'vitest'
import { formatRelativeTime } from './format'

describe('formatRelativeTime', () => {
  const now = new Date('2026-11-01T12:00:00Z')

  it('names the largest whole unit since the timestamp', () => {
    expect(formatRelativeTime('2026-11-01T11:59:30Z', now)).toBe('just now')
    expect(formatRelativeTime('2026-11-01T11:55:00Z', now)).toMatch(/5 minutes ago/)
    expect(formatRelativeTime('2026-11-01T09:00:00Z', now)).toMatch(/3 hours ago/)
    expect(formatRelativeTime('2026-10-30T12:00:00Z', now)).toMatch(/2 days ago/)
  })
})
