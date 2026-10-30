import { describe, expect, it } from 'vitest'
import { filterOptions, matchesColumnFilter } from './data-table'

describe('matchesColumnFilter', () => {
  it('text: keeps values containing the text, ignoring case, list values included', () => {
    expect(matchesColumnFilter('text', 'Customer', 'tom')).toBe(true)
    expect(matchesColumnFilter('text', 'Customer', 'agent')).toBe(false)
    expect(matchesColumnFilter('text', ['HAS_TRIP → Trip', 'SERVES → Stop'], 'stop')).toBe(true)
    expect(matchesColumnFilter('text', undefined, 'x')).toBe(false)
  })

  it('values: keeps values that are one of the picked ones, or a list holding one', () => {
    expect(matchesColumnFilter('values', 'Party', ['Party', 'Vehicle'])).toBe(true)
    expect(matchesColumnFilter('values', 'Ticket', ['Party'])).toBe(false)
    expect(matchesColumnFilter('values', undefined, ['Party'])).toBe(false)
    expect(matchesColumnFilter('values', ['a', 'b'], ['b'])).toBe(true)
  })

  it('toggle: keeps only rows where the value is true', () => {
    expect(matchesColumnFilter('toggle', true, true)).toBe(true)
    expect(matchesColumnFilter('toggle', false, true)).toBe(false)
    expect(matchesColumnFilter('toggle', undefined, true)).toBe(false)
  })
})

describe('filterOptions', () => {
  it('lists each distinct value once, sorted, flattening lists and skipping blanks', () => {
    expect(filterOptions(['Party', undefined, 'Agent', 'Party', ['Zone', 'Agent'], ''])).toEqual([
      'Agent',
      'Party',
      'Zone',
    ])
  })
})
