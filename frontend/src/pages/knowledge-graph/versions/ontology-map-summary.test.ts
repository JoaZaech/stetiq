import { describe, expect, it } from 'vitest'
import type { OntologyDiff } from '@/api/ontology-diff'
import type { Ontology } from '@/api/ontology-versions'
import { compareOntologies } from './ontology-map-comparison'
import { levelOf, summarizeChanges, summaryConceptOf } from './ontology-map-summary'

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
      { level: 'additive', count: 2 },
      // HAS_TRIP only gained a description.
      { level: 'documentation-only', count: 1 },
    ])
  })

  it('groups the changes by the class or relation they belong to, the most severe Concept first', () => {
    const { concepts } = summarizeChanges(compareOntologies(V2, V3, DIFF))

    expect(concepts.map((c) => [c.kind, c.label, c.level])).toEqual([
      // Equally severe Concepts in label order.
      ['node_type', 'Stop', 'breaking'],
      ['node_type', 'Trip', 'breaking'],
    ])
  })

  it('sets the documentation-only changes apart, grouped by Concept', () => {
    const described: Ontology = {
      ...V3,
      node_types: V3.node_types.map((n) =>
        n.label === 'Stop'
          ? { ...n, properties: [{ name: 'wheelchair_boarding', type: 'INTEGER', description: 'Step-free access' }] }
          : n.label === 'Route'
            ? { ...n, description: 'A line riders know by name' }
            : n,
      ),
    }
    const { counts, concepts, documentationOnly } = summarizeChanges(
      compareOntologies(V2, described, {
        classification: 'breaking',
        changes: [
          { concept: 'Route', concept_kind: 'node_type', kind: 'changed', classification: 'additive', detail: 'description changed' },
          ...DIFF.changes,
        ],
      }),
    )

    expect(counts.at(-1)).toEqual({ level: 'documentation-only', count: 2 })
    expect(documentationOnly.map((c) => [c.label, c.level, c.statements.map((s) => s.text)])).toEqual([
      ['HAS_TRIP', 'documentation-only', ['description changed']],
      ['Route', 'documentation-only', ['description changed']],
    ])
    // Stop's attribute was added with its description, so that change is not documentation-only.
    expect(concepts.map((c) => c.label)).toEqual(['Stop', 'Trip'])
  })

  it("orders a Concept's changes most severe first, and says each in words", () => {
    const deprecating: OntologyDiff = {
      classification: 'breaking',
      changes: [
        ...DIFF.changes,
        { concept: 'Stop', concept_kind: 'node_type', kind: 'deprecated', classification: 'deprecating', detail: 'node type Stop deprecated; replaced by Platform' },
      ],
    }
    const { concepts, documentationOnly } = summarizeChanges(
      compareOntologies(V2, { ...V3, node_types: V3.node_types.map((n) => (n.label === 'Stop' ? { ...n, deprecated: true } : n)) }, deprecating),
    )

    expect(concepts[0].statements.map((s) => [s.attribute, s.text, s.level])).toEqual([
      ['wheelchairBoarding', 'removed', 'breaking'],
      [null, 'deprecated; replaced by Platform', 'deprecating'],
      ['wheelchair_boarding', 'added', 'additive'],
    ])
    expect(documentationOnly[0].statements.map((s) => [s.attribute, s.text])).toEqual([[null, 'description changed']])
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

    expect(summary).toEqual({ counts: [], concepts: [], documentationOnly: [] })
  })
})

describe('levelOf', () => {
  it("gives a change the Diff's classification, or documentation-only when only a description differs", () => {
    const comparison = compareOntologies(V2, V3, DIFF)

    expect(DIFF.changes.map((c) => [c.concept, levelOf(comparison, c)])).toEqual([
      ['Stop.wheelchairBoarding', 'breaking'],
      ['Stop.wheelchair_boarding', 'additive'],
      ['Trip.bikesAllowed', 'breaking'],
      ['Trip.bikes_allowed', 'additive'],
      ['HAS_TRIP', 'documentation-only'],
    ])
  })
})

describe('linking the summary and the Map', () => {
  it('selects a class entry as its class, and a relation entry as its first changed link', () => {
    const target: Ontology = { ...V3, patterns: [...V3.patterns, ['Stop', 'HAS_TRIP', 'Trip']] }
    const { concepts } = summarizeChanges(
      compareOntologies(V2, target, {
        classification: 'breaking',
        changes: [
          ...DIFF.changes.filter((c) => c.concept !== 'HAS_TRIP'),
          { concept: 'HAS_TRIP', concept_kind: 'relationship_type', kind: 'changed', classification: 'additive', detail: 'endpoint pattern (Stop)-[HAS_TRIP]->(Trip) added' },
        ],
      }),
    )

    expect(Object.fromEntries(concepts.map((c) => [c.label, c.selection]))).toEqual({
      Stop: { kind: 'class', label: 'Stop' },
      Trip: { kind: 'class', label: 'Trip' },
      // (Route)-[HAS_TRIP]->(Trip) is unchanged.
      HAS_TRIP: { kind: 'link', id: '(Stop)-[HAS_TRIP]->(Trip)' },
    })
  })

  it("finds the entry of a selected class, or of a selected link's relation", () => {
    const comparison = compareOntologies(V2, V3, DIFF)
    const summary = summarizeChanges(comparison)
    const labelOf = (selection: Parameters<typeof summaryConceptOf>[2]) =>
      summaryConceptOf(comparison, summary, selection)?.label ?? null

    expect(labelOf({ kind: 'class', label: 'Trip' })).toBe('Trip')
    expect(labelOf({ kind: 'link', id: '(Route)-[HAS_TRIP]->(Trip)' })).toBe('HAS_TRIP')
    // Unchanged: no entry.
    expect(labelOf({ kind: 'class', label: 'Route' })).toBeNull()
    expect(labelOf({ kind: 'link', id: '(Trip)-[SERVES]->(Stop)' })).toBeNull()
    expect(labelOf({ kind: 'path', from: 'Route', to: 'Stop' })).toBeNull()
    expect(labelOf(null)).toBeNull()
  })
})
