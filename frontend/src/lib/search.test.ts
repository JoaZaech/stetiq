import { describe, expect, it } from 'vitest'
import { matchesSearch, pageOf } from './search'

describe('matchesSearch', () => {
  it('matches everything on an empty query', () => {
    expect(matchesSearch('  ', ['a'])).toBe(true)
  })

  it('needs every word, case-blind, across fields', () => {
    expect(matchesSearch('Claude opus', ['claude', 'claude-opus-5-5'])).toBe(true)
    expect(matchesSearch('claude sonnet', ['claude', 'claude-opus-5-5'])).toBe(false)
  })

  it('skips absent fields and reads numbers', () => {
    expect(matchesSearch('3', [null, undefined, 3])).toBe(true)
  })
})

describe('pageOf', () => {
  const items = Array.from({ length: 120 }, (_, i) => i)

  it('slices one page', () => {
    expect(pageOf(items, 2, 50)).toEqual({ items: items.slice(50, 100), page: 2, pageCount: 3 })
  })

  it('clamps the page to the pages there are', () => {
    expect(pageOf(items, 9, 50).page).toBe(3)
    expect(pageOf(items, 0, 50).page).toBe(1)
    expect(pageOf([], 1, 50)).toEqual({ items: [], page: 1, pageCount: 1 })
  })
})
