import { describe, expect, it } from 'vitest'
import { parseVersionNumber } from './version-number'

describe('parseVersionNumber', () => {
  it('reads a version number from a URL part', () => {
    expect(parseVersionNumber('3')).toBe(3)
    expect(parseVersionNumber('12')).toBe(12)
  })

  it('is undefined for anything that is not a plain number', () => {
    for (const raw of [undefined, null, '', 'v3', '3.0', '-1', ' 3', '1e3', 'abc']) {
      expect(parseVersionNumber(raw)).toBeUndefined()
    }
  })
})
