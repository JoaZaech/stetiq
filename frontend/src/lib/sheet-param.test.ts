import { describe, expect, it } from 'vitest'
import { formatSheet, parseSheet, parseSheetParams } from './sheet-param'

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

describe('parseSheetParams', () => {
  it('reads the open sheet and the sheet its Back returns to', () => {
    const params = new URLSearchParams('sheet=question:agent-names&sheet-back=consumer:triage-bot')
    expect(parseSheetParams(params, KINDS)).toEqual({
      sheet: { kind: 'question', id: 'agent-names' },
      back: { kind: 'consumer', id: 'triage-bot' },
    })
  })

  it('has no Back without one, or without an open sheet', () => {
    expect(parseSheetParams(new URLSearchParams('sheet=consumer:triage-bot'), KINDS).back).toBeNull()
    expect(parseSheetParams(new URLSearchParams('sheet-back=consumer:triage-bot'), KINDS)).toEqual({
      sheet: null,
      back: null,
    })
  })
})
