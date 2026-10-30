import { describe, expect, it } from 'vitest'
import type { OntologyDiff } from '@/api/ontology-diff'
import type { Ontology } from '@/api/ontology-versions'
import { changesOf, compareOntologies, layoutOntologyMap } from './ontology-map'

// Canonical form, as the server sends it: Concepts sorted by label.
const BASE: Ontology = {
  node_types: [
    { label: 'Customer' },
    { label: 'LegacyTicket' },
    { label: 'Product' },
    { label: 'Ticket', properties: [{ name: 'priority', type: 'STRING' }] },
  ],
  relationship_types: [{ label: 'ABOUT' }, { label: 'FILED' }, { label: 'OPENED' }],
  patterns: [
    ['Customer', 'FILED', 'LegacyTicket'],
    ['Customer', 'OPENED', 'Ticket'],
    ['Ticket', 'ABOUT', 'Product'],
  ],
}

const TARGET: Ontology = {
  node_types: [
    { label: 'Agent' },
    { label: 'Customer', deprecated: true },
    { label: 'Product' },
    { label: 'Ticket' },
  ],
  relationship_types: [{ label: 'ABOUT' }, { label: 'ASSIGNED' }, { label: 'OPENED' }],
  patterns: [
    ['Agent', 'OPENED', 'Ticket'],
    ['Customer', 'OPENED', 'Ticket'],
    ['Ticket', 'ABOUT', 'Product'],
    ['Ticket', 'ASSIGNED', 'Agent'],
  ],
}

// What the core's Ontology Diff reports from BASE to TARGET.
const DIFF: OntologyDiff = {
  classification: 'breaking',
  changes: [
    { concept: 'Agent', concept_kind: 'node_type', kind: 'added', classification: 'additive', detail: 'node type Agent added' },
    { concept: 'Customer', concept_kind: 'node_type', kind: 'deprecated', classification: 'deprecating', detail: 'node type Customer deprecated' },
    { concept: 'LegacyTicket', concept_kind: 'node_type', kind: 'removed', classification: 'breaking', detail: 'node type LegacyTicket removed' },
    { concept: 'Ticket.priority', concept_kind: 'property', kind: 'removed', classification: 'breaking', detail: 'property Ticket.priority removed' },
    { concept: 'ASSIGNED', concept_kind: 'relationship_type', kind: 'added', classification: 'additive', detail: 'relationship type ASSIGNED added' },
    { concept: 'FILED', concept_kind: 'relationship_type', kind: 'removed', classification: 'breaking', detail: 'relationship type FILED removed' },
    { concept: 'OPENED', concept_kind: 'relationship_type', kind: 'changed', classification: 'additive', detail: 'endpoint pattern (Agent)-[OPENED]->(Ticket) added' },
  ],
}

describe('compareOntologies', () => {
  it('draws the classes of both versions as one network, each added, removed or unchanged', () => {
    const { map, changes } = compareOntologies(BASE, TARGET, DIFF)

    expect(map.nodes.map((n) => n.label).sort()).toEqual(['Agent', 'Customer', 'LegacyTicket', 'Product', 'Ticket'])
    expect(changes.classes.Agent).toEqual({ kind: 'added', severity: 'additive' })
    expect(changes.classes.LegacyTicket).toEqual({ kind: 'removed', severity: 'breaking' })
    expect(changes.classes.Product).toEqual({ kind: 'unchanged', severity: null })
  })

  it("marks a class modified, with that change's severity, when one of its attributes changes", () => {
    const { changes } = compareOntologies(BASE, TARGET, DIFF)

    // Ticket.priority was removed: breaking.
    expect(changes.classes.Ticket).toEqual({ kind: 'modified', severity: 'breaking' })
  })

  it('marks a deprecated class modified, as deprecating', () => {
    const { changes } = compareOntologies(BASE, TARGET, DIFF)

    expect(changes.classes.Customer).toEqual({ kind: 'modified', severity: 'deprecating' })
  })

  it("draws the Patterns of both versions, added or removed as the Ontologies say, in their relation's severity", () => {
    const { map, changes } = compareOntologies(BASE, TARGET, DIFF)

    expect(map.links.map((l) => l.id).sort()).toEqual([
      '(Agent)-[OPENED]->(Ticket)',
      '(Customer)-[FILED]->(LegacyTicket)',
      '(Customer)-[OPENED]->(Ticket)',
      '(Ticket)-[ABOUT]->(Product)',
      '(Ticket)-[ASSIGNED]->(Agent)',
    ])
    expect(changes.links).toEqual({
      // A new Pattern of a relation both versions have: the Diff records it against OPENED.
      '(Agent)-[OPENED]->(Ticket)': { kind: 'added', severity: 'additive' },
      '(Customer)-[FILED]->(LegacyTicket)': { kind: 'removed', severity: 'breaking' },
      // OPENED's only change is another Pattern's: this one is unchanged.
      '(Customer)-[OPENED]->(Ticket)': { kind: 'unchanged', severity: null },
      '(Ticket)-[ABOUT]->(Product)': { kind: 'unchanged', severity: null },
      '(Ticket)-[ASSIGNED]->(Agent)': { kind: 'added', severity: 'additive' },
    })
  })

  it("marks every Pattern of a relation modified, in that change's severity, when one of its attributes changes", () => {
    const target: Ontology = {
      ...TARGET,
      relationship_types: [
        { label: 'ABOUT' },
        { label: 'ASSIGNED' },
        { label: 'OPENED', properties: [{ name: 'channel', type: 'STRING', required: true }] },
      ],
    }
    const { changes } = compareOntologies(BASE, target, {
      classification: 'breaking',
      changes: [
        ...DIFF.changes,
        { concept: 'OPENED.channel', concept_kind: 'property', kind: 'added', classification: 'breaking', detail: 'required property OPENED.channel added' },
      ],
    })

    expect(changes.links['(Customer)-[OPENED]->(Ticket)']).toEqual({ kind: 'modified', severity: 'breaking' })
    // The added Pattern is added, in the most severe of its own change and its relation's.
    expect(changes.links['(Agent)-[OPENED]->(Ticket)']).toEqual({ kind: 'added', severity: 'breaking' })
  })

  it("draws the subclass links of both versions, a moved class's old one removed, in that class's severity", () => {
    const { map, changes } = compareOntologies(
      { ...BASE, node_types: [{ label: 'Bug', parent: 'Ticket' }, { label: 'Incident', parent: 'Ticket' }, { label: 'Product' }, { label: 'Ticket' }] },
      { ...TARGET, node_types: [{ label: 'Bug', parent: 'Product' }, { label: 'Incident', parent: 'Ticket' }, { label: 'Product' }, { label: 'Ticket' }] },
      {
        classification: 'breaking',
        changes: [
          { concept: 'Bug', concept_kind: 'node_type', kind: 'changed', classification: 'breaking', detail: 'parent Ticket -> Product' },
        ],
      },
    )

    expect(map.subclassLinks.map((l) => l.id).sort()).toEqual(['Bug -> Product', 'Bug -> Ticket', 'Incident -> Ticket'])
    expect(changes.subclassLinks).toEqual({
      'Bug -> Product': { kind: 'added', severity: 'breaking' },
      'Bug -> Ticket': { kind: 'removed', severity: 'breaking' },
      'Incident -> Ticket': { kind: 'unchanged', severity: null },
    })
  })

  it('bends a removed Pattern apart from the links that replace it between the same classes', () => {
    const { map } = compareOntologies(
      { ...BASE, patterns: [['Customer', 'FILED', 'Ticket']] },
      { ...TARGET, patterns: [['Customer', 'OPENED', 'Ticket']] },
      DIFF,
    )
    const bends = map.links.map((l) => (l.route.kind === 'line' ? l.route.bend : null))

    expect(new Set(bends).size).toBe(2)
  })
})

describe('layoutOntologyMap: a comparison', () => {
  it('gives each class of either version one position, the same every time', async () => {
    const first = await layoutOntologyMap(compareOntologies(BASE, TARGET, DIFF).map)
    const second = await layoutOntologyMap(compareOntologies(structuredClone(BASE), structuredClone(TARGET), DIFF).map)

    expect(Object.keys(first).sort()).toEqual(['Agent', 'Customer', 'LegacyTicket', 'Product', 'Ticket'])
    expect(second).toEqual(first)
  })
})

describe('changesOf', () => {
  it("lists the Diff's changes to a selected class, those to its attributes included", () => {
    const comparison = compareOntologies(BASE, TARGET, DIFF)

    expect(changesOf(comparison, { kind: 'class', label: 'Ticket' }).map((c) => c.detail)).toEqual([
      'property Ticket.priority removed',
    ])
    expect(changesOf(comparison, { kind: 'class', label: 'Product' })).toEqual([])
  })

  it('gives an attribute change to the class or the relation that declares it, when the two share a label', () => {
    // A class and a relation both named Rating: the Diff names either one's attributes `Rating.<name>`.
    const base: Ontology = {
      node_types: [{ label: 'Customer' }, { label: 'Rating', properties: [{ name: 'stars', type: 'INTEGER' }] }],
      relationship_types: [{ label: 'Rating', properties: [{ name: 'weight', type: 'FLOAT' }] }],
      patterns: [['Customer', 'Rating', 'Rating']],
    }
    const target: Ontology = {
      ...base,
      relationship_types: [{ label: 'Rating' }],
      constraints: [{ type: 'UNIQUENESS', node_type: 'Rating', property_name: 'stars' }],
    }
    const comparison = compareOntologies(base, target, {
      classification: 'breaking',
      changes: [
        { concept: 'Rating.weight', concept_kind: 'property', kind: 'removed', classification: 'breaking', detail: 'property Rating.weight removed' },
        { concept: 'Rating.stars', concept_kind: 'property', kind: 'changed', classification: 'breaking', detail: 'UNIQUENESS constraint added' },
      ],
    })

    expect(changesOf(comparison, { kind: 'class', label: 'Rating' }).map((c) => c.detail)).toEqual([
      'UNIQUENESS constraint added',
    ])
    expect(
      changesOf(comparison, { kind: 'link', id: '(Customer)-[Rating]->(Rating)' }).map((c) => c.detail),
    ).toEqual(['property Rating.weight removed'])
  })

  it("lists the Diff's changes to a selected link: its own Pattern's, and its relation's", () => {
    const comparison = compareOntologies(BASE, TARGET, DIFF)

    expect(changesOf(comparison, { kind: 'link', id: '(Agent)-[OPENED]->(Ticket)' }).map((c) => c.detail)).toEqual([
      'endpoint pattern (Agent)-[OPENED]->(Ticket) added',
    ])
    expect(changesOf(comparison, { kind: 'link', id: '(Customer)-[OPENED]->(Ticket)' })).toEqual([])
    expect(changesOf(comparison, null)).toEqual([])
  })
})
