import { describe, expect, it } from 'vitest'
import type { OntologyDiff } from '@/api/ontology-diff'
import type { Ontology } from '@/api/ontology-versions'
import { changesOf, compareOntologies } from './ontology-map-comparison'
import {
  attributeChange,
  attributeDescribed,
  conceptChange,
  conceptDescribed,
  endpointChange,
} from './ontology-diff.fixtures'
import { layoutOntologyMap } from '../map/ontology-map-layout'

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
    conceptChange('node_type', 'Agent', 'added', 'additive'),
    conceptChange('node_type', 'Customer', 'deprecated', 'deprecating', 'deprecated'),
    conceptChange('node_type', 'LegacyTicket', 'removed', 'breaking'),
    attributeChange('node_type', 'Ticket', 'priority', 'removed', 'breaking'),
    conceptChange('relationship_type', 'ASSIGNED', 'added', 'additive'),
    conceptChange('relationship_type', 'FILED', 'removed', 'breaking'),
    endpointChange(['Agent', 'OPENED', 'Ticket'], 'added'),
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
        attributeChange('relationship_type', 'OPENED', 'channel', 'added', 'breaking', { required: true }),
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
          conceptChange('node_type', 'Bug', 'changed', 'breaking', 'parent Ticket -> Product'),
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

describe('compareOntologies: changed attributes', () => {
  // A transit Stop whose wheelchair attribute was renamed, its name made required and a
  // code made unique; its description and the Route class are untouched.
  const base: Ontology = {
    node_types: [
      { label: 'Route', properties: [{ name: 'short_name', type: 'STRING' }] },
      {
        label: 'Stop',
        properties: [
          { name: 'code', type: 'STRING' },
          { name: 'description', type: 'STRING' },
          { name: 'name', type: 'STRING' },
          { name: 'wheelchairBoarding', type: 'INTEGER' },
        ],
      },
    ],
    relationship_types: [{ label: 'SERVES' }],
    patterns: [['Route', 'SERVES', 'Stop']],
  }
  const target: Ontology = {
    ...base,
    node_types: [
      base.node_types[0],
      {
        label: 'Stop',
        properties: [
          { name: 'code', type: 'STRING' },
          { name: 'description', type: 'STRING' },
          { name: 'name', type: 'STRING', required: true },
          { name: 'wheelchair_boarding', type: 'INTEGER' },
        ],
      },
    ],
    constraints: [{ type: 'UNIQUENESS', node_type: 'Stop', property_name: 'code' }],
  }
  // What the core's Ontology Diff reports from base to target.
  const diff: OntologyDiff = {
    classification: 'breaking',
    changes: [
      attributeChange('node_type', 'Stop', 'name', 'changed', 'breaking', { detail: 'now required' }),
      attributeChange('node_type', 'Stop', 'wheelchairBoarding', 'removed', 'breaking'),
      attributeChange('node_type', 'Stop', 'wheelchair_boarding', 'added', 'additive'),
      attributeChange('node_type', 'Stop', 'code', 'changed', 'breaking', { detail: 'UNIQUENESS constraint added' }),
    ],
  }

  it('lists exactly the attributes that changed on a class, each removed, added or modified, by name', () => {
    const { changes } = compareOntologies(base, target, diff)

    expect(changes.attributes.Stop).toEqual([
      { name: 'code', kind: 'modified', severity: 'breaking', details: ['UNIQUENESS constraint added'] },
      { name: 'name', kind: 'modified', severity: 'breaking', details: ['now required'] },
      { name: 'wheelchairBoarding', kind: 'removed', severity: 'breaking', details: [] },
      { name: 'wheelchair_boarding', kind: 'added', severity: 'additive', details: [] },
    ])
  })

  it('lists no attributes for a class none of whose attributes changed', () => {
    const { changes } = compareOntologies(base, target, diff)

    expect(changes.attributes.Route).toEqual([])
  })

  it("gives a modified attribute every one of its changes, in the most severe one's severity", () => {
    const { changes } = compareOntologies(base, target, {
      classification: 'breaking',
      changes: [
        attributeChange('node_type', 'Stop', 'name', 'changed', 'additive', { detail: 'now optional' }),
        attributeChange('node_type', 'Stop', 'name', 'changed', 'breaking', { detail: 'type STRING -> INTEGER (narrowed)' }),
      ],
    })

    expect(changes.attributes.Stop).toEqual([
      { name: 'name', kind: 'modified', severity: 'breaking', details: ['now optional', 'type STRING -> INTEGER (narrowed)'] },
    ])
  })
})

describe('cosmetic changes', () => {
  // A transit network whose class Stop, attribute Trip.headsign and relation HAS_TRIP
  // gain a description; SERVES gains one too, with a new Pattern beside it.
  const base: Ontology = {
    node_types: [{ label: 'Route' }, { label: 'Stop' }, { label: 'Trip', properties: [{ name: 'headsign', type: 'STRING' }] }],
    relationship_types: [{ label: 'HAS_TRIP' }, { label: 'SERVES' }],
    patterns: [
      ['Route', 'HAS_TRIP', 'Trip'],
      ['Trip', 'SERVES', 'Stop'],
    ],
  }
  const target: Ontology = {
    node_types: [
      { label: 'Route' },
      { label: 'Stop', description: 'Where riders board' },
      { label: 'Trip', properties: [{ name: 'headsign', type: 'STRING', description: 'The sign on the vehicle' }] },
    ],
    relationship_types: [
      { label: 'HAS_TRIP', description: 'The scheduled trips of a route' },
      { label: 'SERVES', description: 'The stops a trip calls at' },
    ],
    patterns: [
      ['Route', 'HAS_TRIP', 'Trip'],
      ['Route', 'SERVES', 'Stop'],
      ['Trip', 'SERVES', 'Stop'],
    ],
  }
  // What the core's Ontology Diff reports from base to target.
  const diff: OntologyDiff = {
    classification: 'additive',
    changes: [
      conceptDescribed('node_type', 'Stop'),
      attributeDescribed('node_type', 'Trip', 'headsign'),
      conceptDescribed('relationship_type', 'HAS_TRIP'),
      conceptDescribed('relationship_type', 'SERVES'),
      endpointChange(['Route', 'SERVES', 'Stop'], 'added'),
    ],
  }

  it('draws a Concept with only cosmetic changes as documentation-only, with no severity', () => {
    const { changes } = compareOntologies(base, target, diff)

    expect(changes.classes.Stop).toEqual({ kind: 'documentation-only', severity: null })
    expect(changes.links['(Route)-[HAS_TRIP]->(Trip)']).toEqual({ kind: 'documentation-only', severity: null })
    // A class whose attributes had only cosmetic changes lists none of them.
    expect(changes.classes.Trip).toEqual({ kind: 'documentation-only', severity: null })
    expect(changes.attributes.Trip).toEqual([])
  })

  it("gives an endpoint change to its own link only, so a relation's other links stay documentation-only", () => {
    const { changes } = compareOntologies(base, target, diff)

    expect(changes.links['(Route)-[SERVES]->(Stop)']).toEqual({ kind: 'added', severity: 'additive' })
    expect(changes.links['(Trip)-[SERVES]->(Stop)']).toEqual({ kind: 'documentation-only', severity: null })
  })

  it("follows the Diff's classification, not the two Ontologies: a description change it calls additive is not cosmetic", () => {
    const { changes } = compareOntologies(base, target, {
      classification: 'additive',
      changes: [conceptChange('node_type', 'Stop', 'changed', 'additive', 'description changed')],
    })

    expect(changes.classes.Stop).toEqual({ kind: 'modified', severity: 'additive' })
  })
})

describe("the Diff's wording", () => {
  it('draws the same comparison whatever words a change is in: code reads the fields, never the detail', () => {
    const withRelationAttribute: OntologyDiff = {
      classification: 'breaking',
      changes: [...DIFF.changes, attributeChange('relationship_type', 'OPENED', 'channel', 'added', 'breaking', { required: true })],
    }
    const reworded: OntologyDiff = {
      ...withRelationAttribute,
      changes: withRelationAttribute.changes.map((c) => ({ ...c, detail: 'something changed' })),
    }

    const comparison = compareOntologies(BASE, TARGET, reworded)

    expect(comparison.changes).toEqual(compareOntologies(BASE, TARGET, withRelationAttribute).changes)
    expect(comparison.changes.links['(Customer)-[OPENED]->(Ticket)']).toEqual({ kind: 'modified', severity: 'breaking' })
    expect(changesOf(comparison, { kind: 'link', id: '(Agent)-[OPENED]->(Ticket)' }).map((c) => c.concept)).toEqual([
      'OPENED',
      'OPENED.channel',
    ])
    expect(changesOf(comparison, { kind: 'link', id: '(Customer)-[OPENED]->(Ticket)' }).map((c) => c.concept)).toEqual([
      'OPENED.channel',
    ])
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
        attributeChange('relationship_type', 'Rating', 'weight', 'removed', 'breaking'),
        attributeChange('node_type', 'Rating', 'stars', 'changed', 'breaking', { detail: 'UNIQUENESS constraint added' }),
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
