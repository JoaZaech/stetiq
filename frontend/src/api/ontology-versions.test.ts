import { describe, expect, it } from 'vitest'
import { withPatternTriples, type WireOntologyVersion } from './ontology-versions'

const version = (patterns: WireOntologyVersion['ontology']['patterns']): WireOntologyVersion => ({
  knowledge_graph: 'maintenance',
  number: 1,
  content_hash: 'abc',
  origin: 'registered',
  created_at: '2026-10-31T00:00:00Z',
  ontology: { node_types: [], relationship_types: [], patterns },
})

describe('withPatternTriples', () => {
  it('turns a pattern declaring a cardinality into its [source, relationship, target] triple', () => {
    const fetched = version([
      ['Machine', 'PART_OF', 'Line'],
      {
        source: 'WorkOrder',
        relationship: 'PERFORMED_ON',
        target: 'Machine',
        cardinality: { out: { min: 1, max: 1 } },
      },
    ])

    expect(withPatternTriples(fetched).ontology.patterns).toEqual([
      ['Machine', 'PART_OF', 'Line'],
      ['WorkOrder', 'PERFORMED_ON', 'Machine'],
    ])
  })
})
