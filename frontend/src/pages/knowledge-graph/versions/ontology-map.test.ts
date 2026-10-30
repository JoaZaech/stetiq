import { describe, expect, it } from 'vitest'
import type { Ontology } from '@/api/ontology-versions'
import {
  detailsOf,
  focusOf,
  layoutOntologyMap,
  neighboursOf,
  NODE_SIZE,
  ontologyMap,
  type Point,
} from './ontology-map'

// Canonical form, as the server sends it: Concepts sorted by label.
const ONTOLOGY: Ontology = {
  node_types: [{ label: 'Customer' }, { label: 'Product' }, { label: 'Ticket' }],
  relationship_types: [{ label: 'ABOUT' }, { label: 'DUPLICATES' }, { label: 'FOLLOWS' }, { label: 'OPENED' }],
  patterns: [
    ['Customer', 'FOLLOWS', 'Ticket'],
    ['Customer', 'OPENED', 'Ticket'],
    ['Ticket', 'ABOUT', 'Product'],
    ['Ticket', 'DUPLICATES', 'Ticket'],
  ],
}

describe('ontologyMap', () => {
  it('draws every class as a node and every Pattern as a link labelled with its relation', () => {
    const map = ontologyMap(ONTOLOGY)

    expect(map.nodes.map((n) => n.label)).toEqual(['Customer', 'Product', 'Ticket'])
    expect(map.links.map((l) => [l.source, l.relation, l.target])).toEqual([
      ['Customer', 'FOLLOWS', 'Ticket'],
      ['Customer', 'OPENED', 'Ticket'],
      ['Ticket', 'ABOUT', 'Product'],
      ['Ticket', 'DUPLICATES', 'Ticket'],
    ])
  })

  it('bends parallel links apart, either way round, and keeps a lone link straight', () => {
    const { links } = ontologyMap({
      ...ONTOLOGY,
      relationship_types: [...ONTOLOGY.relationship_types, { label: 'ESCALATED_BY' }],
      patterns: [...ONTOLOGY.patterns, ['Ticket', 'ESCALATED_BY', 'Customer']],
    })
    const route = (id: string) => links.find((l) => l.id === id)?.route

    // Bends are to the left of each link's own direction, so the reversed link sits
    // on the far side from (Customer)-[FOLLOWS]->(Ticket).
    expect(route('(Customer)-[FOLLOWS]->(Ticket)')).toEqual({ kind: 'line', bend: -1 })
    expect(route('(Customer)-[OPENED]->(Ticket)')).toEqual({ kind: 'line', bend: 0 })
    expect(route('(Ticket)-[ESCALATED_BY]->(Customer)')).toEqual({ kind: 'line', bend: -1 })
    expect(route('(Ticket)-[ABOUT]->(Product)')).toEqual({ kind: 'line', bend: 0 })
  })

  it('draws a Pattern from a class to itself as a loop, larger for each further one', () => {
    const { links } = ontologyMap({
      ...ONTOLOGY,
      relationship_types: [...ONTOLOGY.relationship_types, { label: 'SPLIT_FROM' }],
      patterns: [...ONTOLOGY.patterns, ['Ticket', 'SPLIT_FROM', 'Ticket']],
    })
    const route = (id: string) => links.find((l) => l.id === id)?.route

    expect(route('(Ticket)-[DUPLICATES]->(Ticket)')).toEqual({ kind: 'loop', size: 1 })
    expect(route('(Ticket)-[SPLIT_FROM]->(Ticket)')).toEqual({ kind: 'loop', size: 2 })
  })
})

describe('neighboursOf', () => {
  it('finds the classes a class links to and the classes that link to it', () => {
    const map = ontologyMap(ONTOLOGY)

    // Ticket links out to Product, and Customer links in to it.
    expect(neighboursOf(map, 'Ticket')).toEqual({
      classes: ['Customer', 'Product'],
      links: [
        '(Customer)-[FOLLOWS]->(Ticket)',
        '(Customer)-[OPENED]->(Ticket)',
        '(Ticket)-[ABOUT]->(Product)',
        '(Ticket)-[DUPLICATES]->(Ticket)',
      ],
    })
    // Product has only an incoming link, Customer only outgoing ones.
    expect(neighboursOf(map, 'Product')).toEqual({ classes: ['Ticket'], links: ['(Ticket)-[ABOUT]->(Product)'] })
    expect(neighboursOf(map, 'Customer').classes).toEqual(['Ticket'])
  })
})

describe('focusOf', () => {
  it('keeps a selected class and its neighbours in focus', () => {
    const map = ontologyMap(ONTOLOGY)

    expect(focusOf(map, { kind: 'class', label: 'Product' })).toEqual({
      classes: new Set(['Product', 'Ticket']),
      links: new Set(['(Ticket)-[ABOUT]->(Product)']),
    })
  })

  it('keeps a selected link and the two classes it joins in focus', () => {
    const map = ontologyMap(ONTOLOGY)

    expect(focusOf(map, { kind: 'link', id: '(Customer)-[OPENED]->(Ticket)' })).toEqual({
      classes: new Set(['Customer', 'Ticket']),
      links: new Set(['(Customer)-[OPENED]->(Ticket)']),
    })
  })

  it('keeps everything in focus when nothing is selected, or the selection is gone', () => {
    const map = ontologyMap(ONTOLOGY)

    expect(focusOf(map, null)).toBeNull()
    expect(focusOf(map, { kind: 'class', label: 'Agent' })).toBeNull()
    expect(focusOf(map, { kind: 'link', id: '(Agent)-[OPENED]->(Ticket)' })).toBeNull()
  })
})

// A class hierarchy, Party > Customer > VipCustomer, with properties at each level.
const HIERARCHY: Ontology = {
  node_types: [
    {
      label: 'Customer',
      description: 'Someone who opens tickets',
      parent: 'Party',
      properties: [{ name: 'email', type: 'STRING' }],
    },
    { label: 'Party', properties: [{ name: 'name', type: 'STRING', required: true }] },
    { label: 'Ticket' },
    { label: 'VipCustomer', parent: 'Customer', properties: [{ name: 'tier', type: 'INTEGER', description: '1 to 3' }] },
  ],
  relationship_types: [
    {
      label: 'OPENED',
      description: 'The customer opened the ticket',
      properties: [{ name: 'at', type: 'DATE_TIME', required: true }],
    },
  ],
  patterns: [['Customer', 'OPENED', 'Ticket']],
  constraints: [
    { type: 'UNIQUENESS', node_type: 'VipCustomer', property_name: 'tier' },
    { type: 'UNIQUENESS', node_type: 'Party', property_name: 'name' },
  ],
}

describe('detailsOf', () => {
  it('details a class: its own properties, then those it inherits, marked with the ancestor that declares them', () => {
    expect(detailsOf(HIERARCHY, { kind: 'class', label: 'VipCustomer' })).toEqual({
      kind: 'class',
      label: 'VipCustomer',
      description: undefined,
      deprecated: false,
      parent: 'Customer',
      properties: [
        { name: 'tier', type: 'INTEGER', description: '1 to 3', required: false },
        { name: 'email', type: 'STRING', description: undefined, required: false, inheritedFrom: 'Customer' },
        { name: 'name', type: 'STRING', description: undefined, required: true, inheritedFrom: 'Party' },
      ],
      constraints: ['UNIQUENESS (tier)'],
    })
  })

  it('takes a property a class redeclares from the class, not from its ancestor', () => {
    const ontology: Ontology = {
      ...HIERARCHY,
      node_types: HIERARCHY.node_types.map((n) =>
        n.label === 'Customer' ? { ...n, properties: [{ name: 'name', type: 'STRING' }] } : n,
      ),
    }

    expect(detailsOf(ontology, { kind: 'class', label: 'Customer' })?.properties).toEqual([
      { name: 'name', type: 'STRING', description: undefined, required: false },
    ])
  })

  it('stops at a superclass the Ontology does not declare, and at a cycle', () => {
    const ontology: Ontology = {
      ...HIERARCHY,
      node_types: [
        { label: 'A', parent: 'B', properties: [{ name: 'a', type: 'STRING' }] },
        { label: 'B', parent: 'A', properties: [{ name: 'b', type: 'STRING' }] },
        { label: 'C', parent: 'Missing' },
      ],
    }

    expect(detailsOf(ontology, { kind: 'class', label: 'A' })?.properties.map((p) => p.name)).toEqual(['a', 'b'])
    expect(detailsOf(ontology, { kind: 'class', label: 'C' })?.properties).toEqual([])
  })

  it("details a link: its Pattern, and its relation's description and properties", () => {
    expect(detailsOf(HIERARCHY, { kind: 'link', id: '(Customer)-[OPENED]->(Ticket)' })).toEqual({
      kind: 'link',
      id: '(Customer)-[OPENED]->(Ticket)',
      source: 'Customer',
      relation: 'OPENED',
      target: 'Ticket',
      description: 'The customer opened the ticket',
      deprecated: false,
      properties: [{ name: 'at', type: 'DATE_TIME', description: undefined, required: true }],
    })
  })

  it('has nothing to detail for no selection, or one the Ontology does not have', () => {
    expect(detailsOf(HIERARCHY, null)).toBeNull()
    expect(detailsOf(HIERARCHY, { kind: 'class', label: 'Agent' })).toBeNull()
    expect(detailsOf(HIERARCHY, { kind: 'link', id: '(Ticket)-[OPENED]->(Customer)' })).toBeNull()
  })
})

describe('layoutOntologyMap', () => {
  it('places every class apart from the others', async () => {
    const positions = await layoutOntologyMap(ontologyMap(ONTOLOGY))

    expect(Object.keys(positions).sort()).toEqual(['Customer', 'Product', 'Ticket'])
    const [a, b, c] = Object.values(positions)
    const apart = (p: Point, q: Point) =>
      Math.abs(p.x - q.x) >= NODE_SIZE.width || Math.abs(p.y - q.y) >= NODE_SIZE.height
    expect([apart(a, b), apart(a, c), apart(b, c)]).toEqual([true, true, true])
  })

  it('lays out the same Ontology the same way every time', async () => {
    const first = await layoutOntologyMap(ontologyMap(ONTOLOGY))
    const second = await layoutOntologyMap(ontologyMap(structuredClone(ONTOLOGY)))

    expect(second).toEqual(first)
  })

  it('lays out an Ontology of 100 classes in under a second', async () => {
    const started = performance.now()
    await layoutOntologyMap(ontologyMap(generatedOntology(100)))

    expect(performance.now() - started).toBeLessThan(1000)
  })
})

/** `size` classes in a ring, each related to the next two, with a few self-loops. */
function generatedOntology(size: number): Ontology {
  const label = (i: number) => `Class${String(i % size).padStart(3, '0')}`
  const patterns: [string, string, string][] = []
  for (let i = 0; i < size; i++) {
    patterns.push([label(i), 'NEXT', label(i + 1)], [label(i), 'SKIPS', label(i + 2)])
    if (i % 10 === 0) patterns.push([label(i), 'SELF', label(i)])
  }
  return {
    node_types: Array.from({ length: size }, (_, i) => ({ label: label(i) })),
    relationship_types: [{ label: 'NEXT' }, { label: 'SELF' }, { label: 'SKIPS' }],
    patterns,
  }
}
