import { describe, expect, it } from 'vitest'
import type { OntologyDiff } from '@/api/ontology-diff'
import type { Ontology } from '@/api/ontology-versions'
import { compareOntologies } from './ontology-map-comparison'
import { comparisonRows } from './comparison-rows'

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
    { concept: 'Stop.wheelchairBoarding', concept_kind: 'property', kind: 'removed', classification: 'breaking', detail: 'property Stop.wheelchairBoarding removed' },
    { concept: 'Stop.wheelchair_boarding', concept_kind: 'property', kind: 'added', classification: 'additive', detail: 'optional property Stop.wheelchair_boarding added' },
    { concept: 'Trip.bikesAllowed', concept_kind: 'property', kind: 'removed', classification: 'breaking', detail: 'property Trip.bikesAllowed removed' },
    { concept: 'Trip.bikes_allowed', concept_kind: 'property', kind: 'added', classification: 'additive', detail: 'optional property Trip.bikes_allowed added' },
    { concept: 'HAS_TRIP', concept_kind: 'relationship_type', kind: 'changed', classification: 'additive', detail: 'description changed' },
  ],
}

describe('comparisonRows', () => {
  it("gives one row per Diff change, with its Concept, Concept kind, change, level and detail, the weightiest first", () => {
    const rows = comparisonRows(compareOntologies(V2, V3, DIFF))

    expect(rows.map(({ concept, conceptKind, change, level, detail }) => [concept, conceptKind, change, level, detail])).toEqual([
      ['Stop.wheelchairBoarding', 'attribute', 'removed', 'breaking', 'property Stop.wheelchairBoarding removed'],
      ['Trip.bikesAllowed', 'attribute', 'removed', 'breaking', 'property Trip.bikesAllowed removed'],
      ['Stop.wheelchair_boarding', 'attribute', 'added', 'additive', 'optional property Stop.wheelchair_boarding added'],
      ['Trip.bikes_allowed', 'attribute', 'added', 'additive', 'optional property Trip.bikes_allowed added'],
      // Only a description differs: its own level, whatever the Diff classified it as.
      ['HAS_TRIP', 'relation', 'changed', 'documentation-only', 'description changed'],
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
        { concept: 'SERVES.sequence', concept_kind: 'property', kind: 'added', classification: 'additive', detail: 'optional property SERVES.sequence added' },
      ],
    }

    const [row] = comparisonRows(compareOntologies(base, target, diff))

    expect(row.owner).toEqual({ kind: 'relation', label: 'SERVES' })
  })
})
