import { describe, expect, it } from 'vitest'
import type { OntologyDiff } from '@/api/ontology-diff'
import type { Ontology } from '@/api/ontology-versions'
import { compareOntologies } from './ontology-map-comparison'
import { summarizeChanges } from './ontology-map-summary'

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

describe('summarizeChanges', () => {
  it("counts the Diff's changes per level, most severe first, leaving out levels with none", () => {
    const { counts } = summarizeChanges(compareOntologies(V2, V3, DIFF))

    expect(counts).toEqual([
      { level: 'breaking', count: 2 },
      { level: 'additive', count: 3 },
    ])
  })

  it('groups the changes by the class or relation they belong to, the most severe Concept first', () => {
    const { concepts } = summarizeChanges(compareOntologies(V2, V3, DIFF))

    expect(concepts.map((c) => [c.kind, c.label, c.level])).toEqual([
      // Equally severe Concepts in label order.
      ['node_type', 'Stop', 'breaking'],
      ['node_type', 'Trip', 'breaking'],
      ['relationship_type', 'HAS_TRIP', 'additive'],
    ])
  })

  it("orders a Concept's changes most severe first, and says each in words", () => {
    const deprecating: OntologyDiff = {
      classification: 'breaking',
      changes: [
        ...DIFF.changes,
        { concept: 'Stop', concept_kind: 'node_type', kind: 'deprecated', classification: 'deprecating', detail: 'node type Stop deprecated; replaced by Platform' },
      ],
    }
    const { concepts } = summarizeChanges(
      compareOntologies(V2, { ...V3, node_types: V3.node_types.map((n) => (n.label === 'Stop' ? { ...n, deprecated: true } : n)) }, deprecating),
    )

    expect(concepts[0].statements.map((s) => [s.attribute, s.text, s.level])).toEqual([
      ['wheelchairBoarding', 'removed', 'breaking'],
      [null, 'deprecated; replaced by Platform', 'deprecating'],
      ['wheelchair_boarding', 'added', 'additive'],
    ])
    expect(concepts[2].statements.map((s) => [s.attribute, s.text])).toEqual([[null, 'description changed']])
  })

  it('says how each kind of change landed', () => {
    const base: Ontology = {
      node_types: [{ label: 'Route', properties: [{ name: 'id', type: 'STRING' }] }, { label: 'Trip' }],
      relationship_types: [{ label: 'HAS_TRIP' }],
      patterns: [['Route', 'HAS_TRIP', 'Trip']],
    }
    const target: Ontology = {
      node_types: [
        { label: 'Agency' },
        { label: 'Route', properties: [{ name: 'id', type: 'STRING' }, { name: 'name', type: 'STRING', required: true }] },
      ],
      relationship_types: [{ label: 'OPERATES' }],
      patterns: [['Agency', 'OPERATES', 'Route']],
      constraints: [{ type: 'UNIQUENESS', node_type: 'Route', property_name: 'id' }],
    }
    const { concepts } = summarizeChanges(
      compareOntologies(base, target, {
        classification: 'breaking',
        changes: [
          { concept: 'Agency', concept_kind: 'node_type', kind: 'added', classification: 'additive', detail: 'node type Agency added' },
          { concept: 'Route.name', concept_kind: 'property', kind: 'added', classification: 'breaking', detail: 'required property Route.name added' },
          { concept: 'Trip', concept_kind: 'node_type', kind: 'removed', classification: 'breaking', detail: 'node type Trip removed' },
          { concept: 'HAS_TRIP', concept_kind: 'relationship_type', kind: 'removed', classification: 'breaking', detail: 'relationship type HAS_TRIP removed' },
          { concept: 'OPERATES', concept_kind: 'relationship_type', kind: 'added', classification: 'additive', detail: 'relationship type OPERATES added' },
          { concept: 'Route.id', concept_kind: 'property', kind: 'changed', classification: 'breaking', detail: 'UNIQUENESS constraint added' },
        ],
      }),
    )
    const said = Object.fromEntries(
      concepts.map((c) => [c.label, c.statements.map((s) => (s.attribute ? `${s.attribute}: ${s.text}` : s.text))]),
    )

    expect(said).toEqual({
      Agency: ['class added'],
      Route: ['name: added, required', 'id: UNIQUENESS constraint added'],
      Trip: ['class removed'],
      HAS_TRIP: ['relation removed'],
      OPERATES: ['relation added'],
    })
  })

  it('says when nothing changed', () => {
    const summary = summarizeChanges(compareOntologies(V2, V2, { classification: null, changes: [] }))

    expect(summary).toMatchObject({ counts: [], concepts: [] })
  })
})
