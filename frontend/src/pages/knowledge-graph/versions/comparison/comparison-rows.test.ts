import { describe, expect, it } from 'vitest'
import type { OntologyDiff } from '@/api/ontology-diff'
import type { Ontology } from '@/api/ontology-versions'
import { compareOntologies } from './ontology-map-comparison'
import { comparisonRows } from './comparison-rows'
import { attributeChange, conceptDescribed } from './ontology-diff.fixtures'

// Canonical form, as the server sends it: a city transit network, v2 → v3.
const V2: Ontology = {
  node_types: [
    { label: 'Route' },
    { label: 'Stop', properties: [{ name: 'wheelchairBoarding', type: 'INTEGER' }] },
    { label: 'Trip', properties: [{ name: 'bikesAllowed', type: 'INTEGER' }] },
  ],
  relationship_types: [{ label: 'HAS_TRIP' }, { label: 'SERVES' }],
  patterns: [
    ['Route', 'HAS_TRIP', 'Trip'],
    ['Trip', 'SERVES', 'Stop'],
  ],
}

const V3: Ontology = {
  node_types: [
    { label: 'Route' },
    { label: 'Stop', properties: [{ name: 'wheelchair_boarding', type: 'INTEGER' }] },
    { label: 'Trip', properties: [{ name: 'bikes_allowed', type: 'INTEGER' }] },
  ],
  relationship_types: [{ label: 'HAS_TRIP', description: 'The scheduled trips of a route' }, { label: 'SERVES' }],
  patterns: [
    ['Route', 'HAS_TRIP', 'Trip'],
    ['Trip', 'SERVES', 'Stop'],
  ],
}

// What the core's Ontology Diff reports from V2 to V3.
const DIFF: OntologyDiff = {
  classification: 'breaking',
  changes: [
    attributeChange('node_type', 'Stop', 'wheelchairBoarding', 'removed', 'breaking'),
    attributeChange('node_type', 'Stop', 'wheelchair_boarding', 'added', 'additive'),
    attributeChange('node_type', 'Trip', 'bikesAllowed', 'removed', 'breaking'),
    attributeChange('node_type', 'Trip', 'bikes_allowed', 'added', 'additive'),
    conceptDescribed('relationship_type', 'HAS_TRIP'),
  ],
}

describe('comparisonRows', () => {
  it("gives one row per Diff change, with its Concept, Concept kind, change, level and detail, the weightiest first", () => {
    const rows = comparisonRows(compareOntologies(V2, V3, DIFF))

    expect(rows.map(({ concept, conceptKind, change, level, detail }) => [concept, conceptKind, change, level, detail])).toEqual([
      ['Stop.wheelchairBoarding', 'attribute', 'removed', 'breaking', 'Stop.wheelchairBoarding removed'],
      ['Trip.bikesAllowed', 'attribute', 'removed', 'breaking', 'Trip.bikesAllowed removed'],
      ['Stop.wheelchair_boarding', 'attribute', 'added', 'additive', 'Stop.wheelchair_boarding added'],
      ['Trip.bikes_allowed', 'attribute', 'added', 'additive', 'Trip.bikes_allowed added'],
      // Only a description differs: cosmetic, the least weighty.
      ['HAS_TRIP', 'relation', 'changed', 'cosmetic', 'description changed'],
    ])
  })

  it('shows a change on the Map as its class or relation, an attribute as its owner', () => {
    const rows = comparisonRows(compareOntologies(V2, V3, DIFF))

    expect(rows.find((r) => r.concept === 'Stop.wheelchairBoarding')?.owner).toEqual({ kind: 'class', label: 'Stop' })
    expect(rows.find((r) => r.concept === 'HAS_TRIP')?.owner).toEqual({ kind: 'relation', label: 'HAS_TRIP' })
  })

  it('names an attribute of a relation by its relation', () => {
    const base: Ontology = { ...V2, relationship_types: [{ label: 'HAS_TRIP' }, { label: 'SERVES' }] }
    const target: Ontology = {
      ...V2,
      relationship_types: [{ label: 'HAS_TRIP' }, { label: 'SERVES', properties: [{ name: 'sequence', type: 'INTEGER' }] }],
    }
    const diff: OntologyDiff = {
      classification: 'additive',
      changes: [
        attributeChange('relationship_type', 'SERVES', 'sequence', 'added', 'additive'),
      ],
    }

    const [row] = comparisonRows(compareOntologies(base, target, diff))

    expect(row.owner).toEqual({ kind: 'relation', label: 'SERVES' })
  })

  it('names the owner the Diff states, when a class and a relation share its label', () => {
    const shared: Ontology = {
      node_types: [{ label: 'Rating', properties: [{ name: 'stars', type: 'INTEGER' }] }],
      relationship_types: [{ label: 'Rating', properties: [{ name: 'stars', type: 'INTEGER' }] }],
      patterns: [['Rating', 'Rating', 'Rating']],
    }
    const diff: OntologyDiff = {
      classification: 'breaking',
      changes: [attributeChange('relationship_type', 'Rating', 'stars', 'removed', 'breaking', { detail: 'gone' })],
    }

    const [row] = comparisonRows(compareOntologies(shared, shared, diff))

    expect(row.owner).toEqual({ kind: 'relation', label: 'Rating' })
  })
})
