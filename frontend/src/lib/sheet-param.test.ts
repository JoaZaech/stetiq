import { describe, expect, it } from 'vitest'
import { formatSheet, parseSheet } from './sheet-param'

const KINDS = ['question', 'consumer'] as const

describe('parseSheet', () => {
  it('reads a kind and an id, which may itself hold a colon', () => {
    expect(parseSheet('question:customer-names', KINDS)).toEqual({ kind: 'question', id: 'customer-names' })
    expect(parseSheet('consumer:a:b', KINDS)).toEqual({ kind: 'consumer', id: 'a:b' })
  })

  it('is null when absent, malformed or of a kind the page does not open', () => {
    for (const value of [null, '', 'question', 'question:', ':x', 'task:route-ticket']) {
      expect(parseSheet(value, KINDS)).toBeNull()
    }
  })

  it('round-trips with formatSheet', () => {
    const sheet = { kind: 'question', id: 'ticket-dates' } as const
    expect(parseSheet(formatSheet(sheet), KINDS)).toEqual(sheet)
  })
})
