import { describe, expect, it } from 'vitest'
import { kgCompareUrl } from './knowledge-graph-sections'

describe('kgCompareUrl', () => {
  it('names every compared item with one repeated param, in the order given', () => {
    expect(kgCompareUrl('support', 'versions', [2, 4])).toBe('/kg/support/versions/compare?id=2&id=4')
    expect(kgCompareUrl('support', 'use-case', [1, 3])).toBe('/kg/support/use-case/compare?id=1&id=3')
    expect(kgCompareUrl('support', 'runs', ['a1', 'b2', 'c3'])).toBe(
      '/kg/support/runs/compare?id=a1&id=b2&id=c3',
    )
  })

  it('encodes the Knowledge Graph name and the ids', () => {
    expect(kgCompareUrl('my kg', 'runs', ['a&b'])).toBe('/kg/my%20kg/runs/compare?id=a%26b')
  })
})
