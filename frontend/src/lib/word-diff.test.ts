import { describe, expect, it } from 'vitest'
import { wordDiff } from './word-diff'

describe('wordDiff', () => {
  it('marks the words only the new text has as added, the rest unchanged', () => {
    expect(wordDiff('The trips of a route', 'The scheduled trips of a route')).toEqual([
      { kind: 'unchanged', text: 'The' },
      { kind: 'added', text: 'scheduled' },
      { kind: 'unchanged', text: 'trips of a route' },
    ])
  })

  it('marks a replaced word removed, then the word replacing it added', () => {
    expect(wordDiff('A stop where riders board', 'A station where riders board or alight')).toEqual([
      { kind: 'unchanged', text: 'A' },
      { kind: 'removed', text: 'stop' },
      { kind: 'added', text: 'station' },
      { kind: 'unchanged', text: 'where riders board' },
      { kind: 'added', text: 'or alight' },
    ])
  })

  it('marks every word added when there was no description before, and removed when there is none after', () => {
    expect(wordDiff('', 'The scheduled trips')).toEqual([{ kind: 'added', text: 'The scheduled trips' }])
    expect(wordDiff('The scheduled trips', '')).toEqual([{ kind: 'removed', text: 'The scheduled trips' }])
    expect(wordDiff('', '')).toEqual([])
  })

  it('compares words, not the whitespace between them', () => {
    expect(wordDiff('The  trips\nof a route ', 'The trips of a route')).toEqual([
      { kind: 'unchanged', text: 'The trips of a route' },
    ])
  })
})
