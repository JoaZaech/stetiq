import { describe, expect, it } from 'vitest'
import { kgCompareUrl, switchKnowledgeGraphUrl } from './knowledge-graph-sections'

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

describe('switchKnowledgeGraphUrl', () => {
  it('keeps the open section', () => {
    expect(switchKnowledgeGraphUrl('/kg/support/runs', 'billing')).toBe('/kg/billing/runs')
    expect(switchKnowledgeGraphUrl('/kg/support/use-case', 'billing')).toBe('/kg/billing/use-case')
  })

  it('drops a detail page below the section', () => {
    expect(switchKnowledgeGraphUrl('/kg/support/runs/3f2a9c/conformance', 'billing')).toBe('/kg/billing/runs')
    expect(switchKnowledgeGraphUrl('/kg/support/versions/2', 'billing')).toBe('/kg/billing/versions')
  })

  it('drops a compare page and its query', () => {
    expect(switchKnowledgeGraphUrl('/kg/support/versions/compare?id=1&id=2', 'billing')).toBe(
      '/kg/billing/versions',
    )
  })

  it('opens the default section from a Knowledge Graph root or from outside a Knowledge Graph', () => {
    expect(switchKnowledgeGraphUrl('/kg/support', 'billing')).toBe('/kg/billing/versions')
    expect(switchKnowledgeGraphUrl('/kg/support/no-such-section', 'billing')).toBe('/kg/billing/versions')
    expect(switchKnowledgeGraphUrl('/settings', 'billing')).toBe('/kg/billing/versions')
    expect(switchKnowledgeGraphUrl('/', 'billing')).toBe('/kg/billing/versions')
  })

  it('encodes the target name, and reads an encoded current name', () => {
    expect(switchKnowledgeGraphUrl('/kg/my%20kg/observations', 'a/b c')).toBe('/kg/a%2Fb%20c/observations')
  })
})
