import { describe, expect, it } from 'vitest'
import type { Ontology } from '@/api/ontology-versions'
import {
  detailsOf,
  filterOntologyMap,
  focusOf,
  layoutOntologyMap,
  neighboursOf,
  NODE_SIZE,
  ontologyMap,
  searchMap,
  shortestPaths,
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
const PARTIES: Ontology = {
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
    expect(detailsOf(PARTIES, { kind: 'class', label: 'VipCustomer' })).toEqual({
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
      ...PARTIES,
      node_types: PARTIES.node_types.map((n) =>
        n.label === 'Customer' ? { ...n, properties: [{ name: 'name', type: 'STRING' }] } : n,
      ),
    }

    expect(detailsOf(ontology, { kind: 'class', label: 'Customer' })?.properties).toEqual([
      { name: 'name', type: 'STRING', description: undefined, required: false },
    ])
  })

  it('stops at a superclass the Ontology does not declare, and at a cycle', () => {
    const ontology: Ontology = {
      ...PARTIES,
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
    expect(detailsOf(PARTIES, { kind: 'link', id: '(Customer)-[OPENED]->(Ticket)' })).toEqual({
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
    expect(detailsOf(PARTIES, null)).toBeNull()
    expect(detailsOf(PARTIES, { kind: 'class', label: 'Agent' })).toBeNull()
    expect(detailsOf(PARTIES, { kind: 'link', id: '(Ticket)-[OPENED]->(Customer)' })).toBeNull()
  })
})

describe('searchMap', () => {
  it('matches the classes and links whose Concept the tables would find', () => {
    // "open" is in Customer's description and is the OPENED relation; "tier" is a VipCustomer attribute.
    expect(searchMap(PARTIES, ' OPEN ')).toEqual({
      classes: new Set(['Customer']),
      links: new Set(['(Customer)-[OPENED]->(Ticket)']),
    })
    expect(searchMap(PARTIES, 'tier')).toEqual({ classes: new Set(['VipCustomer']), links: new Set() })
    expect(searchMap(PARTIES, 'nothing like it')).toEqual({ classes: new Set(), links: new Set() })
  })

  it('matches nothing in particular for an empty search', () => {
    expect(searchMap(PARTIES, '  ')).toBeNull()
  })
})

// A hierarchy under Ticket, with a deprecated class and a deprecated relation.
const HIERARCHY: Ontology = {
  node_types: [
    { label: 'Bug', parent: 'Ticket' },
    { label: 'Customer' },
    { label: 'Incident', parent: 'Ticket' },
    { label: 'LegacyTicket', parent: 'Ticket', deprecated: true },
    { label: 'Ticket' },
  ],
  relationship_types: [{ label: 'FILED', deprecated: true }, { label: 'OPENED' }, { label: 'REPORTED' }],
  patterns: [
    ['Customer', 'FILED', 'Ticket'],
    ['Customer', 'OPENED', 'Ticket'],
    ['Customer', 'REPORTED', 'Incident'],
    ['Customer', 'REPORTED', 'LegacyTicket'],
  ],
}

describe('ontologyMap: the subclass hierarchy', () => {
  it('draws each superclass as a subclass link, child to parent, apart from the Pattern links', () => {
    const map = ontologyMap(HIERARCHY)

    expect(map.subclassLinks.map((l) => [l.child, l.parent])).toEqual([
      ['Bug', 'Ticket'],
      ['Incident', 'Ticket'],
      ['LegacyTicket', 'Ticket'],
    ])
    expect(map.links.map((l) => l.id)).toEqual([
      '(Customer)-[FILED]->(Ticket)',
      '(Customer)-[OPENED]->(Ticket)',
      '(Customer)-[REPORTED]->(Incident)',
      '(Customer)-[REPORTED]->(LegacyTicket)',
    ])
  })

  it('draws no subclass link to a superclass the Ontology does not declare', () => {
    const map = ontologyMap({ ...HIERARCHY, node_types: [{ label: 'Bug', parent: 'Ticket' }] })

    expect(map.subclassLinks).toEqual([])
  })
})

describe('ontologyMap: deprecation', () => {
  it('marks deprecated classes, and the links of a deprecated relation', () => {
    const map = ontologyMap(HIERARCHY)

    expect(map.nodes.filter((n) => n.deprecated).map((n) => n.label)).toEqual(['LegacyTicket'])
    expect(map.links.filter((l) => l.deprecated).map((l) => l.id)).toEqual(['(Customer)-[FILED]->(Ticket)'])
  })
})

describe('filterOntologyMap', () => {
  it('hides deprecated classes and relations, and every link to a hidden class', () => {
    const map = filterOntologyMap(ontologyMap(HIERARCHY), { hideDeprecated: true, hideSubclassLinks: false })

    expect(map.nodes.map((n) => n.label)).toEqual(['Bug', 'Customer', 'Incident', 'Ticket'])
    expect(map.links.map((l) => l.id)).toEqual([
      '(Customer)-[OPENED]->(Ticket)',
      '(Customer)-[REPORTED]->(Incident)',
    ])
    expect(map.subclassLinks.map((l) => l.id)).toEqual(['Bug -> Ticket', 'Incident -> Ticket'])
  })

  it('hides subclass links and keeps every class and Pattern link', () => {
    const all = ontologyMap(HIERARCHY)
    const map = filterOntologyMap(all, { hideDeprecated: false, hideSubclassLinks: true })

    expect(map.subclassLinks).toEqual([])
    expect(map.nodes).toEqual(all.nodes)
    expect(map.links).toEqual(all.links)
  })

  it('hides nothing with neither filter on', () => {
    const all = ontologyMap(HIERARCHY)

    expect(filterOntologyMap(all, { hideDeprecated: false, hideSubclassLinks: false })).toEqual(all)
  })
})

describe('shortestPaths', () => {
  it('finds a direct path, through every Pattern joining its two classes, either way round', () => {
    const map = ontologyMap(ONTOLOGY)

    // Ticket to Customer runs against the links' direction: reachability is undirected.
    expect(shortestPaths(map, 'Ticket', 'Customer')).toEqual([
      {
        classes: ['Ticket', 'Customer'],
        steps: [{ links: ['(Customer)-[FOLLOWS]->(Ticket)', '(Customer)-[OPENED]->(Ticket)'], ancestors: [] }],
      },
    ])
  })

  it('finds every shortest path, and no longer one', () => {
    // Customer reaches Product through Order or through Ticket in two steps, and through
    // Ticket and Agent in three.
    const map = ontologyMap({
      node_types: [{ label: 'Agent' }, { label: 'Customer' }, { label: 'Order' }, { label: 'Product' }, { label: 'Ticket' }],
      relationship_types: [{ label: 'ABOUT' }, { label: 'ASSIGNED' }, { label: 'CONTAINS' }, { label: 'OPENED' }, { label: 'PLACED' }, { label: 'SUPPORTS' }],
      patterns: [
        ['Agent', 'SUPPORTS', 'Product'],
        ['Customer', 'OPENED', 'Ticket'],
        ['Customer', 'PLACED', 'Order'],
        ['Order', 'CONTAINS', 'Product'],
        ['Ticket', 'ABOUT', 'Product'],
        ['Ticket', 'ASSIGNED', 'Agent'],
      ],
    })

    expect(shortestPaths(map, 'Customer', 'Product')).toEqual([
      {
        classes: ['Customer', 'Order', 'Product'],
        steps: [
          { links: ['(Customer)-[PLACED]->(Order)'], ancestors: [] },
          { links: ['(Order)-[CONTAINS]->(Product)'], ancestors: [] },
        ],
      },
      {
        classes: ['Customer', 'Ticket', 'Product'],
        steps: [
          { links: ['(Customer)-[OPENED]->(Ticket)'], ancestors: [] },
          { links: ['(Ticket)-[ABOUT]->(Product)'], ancestors: [] },
        ],
      },
    ])
  })

  it("finds a path through a Pattern a class inherits, naming the ancestors it climbs to the Pattern's class", () => {
    // Party > Customer > VipCustomer, and only Party lives at an Address.
    const map = ontologyMap({
      ...PARTIES,
      node_types: [{ label: 'Address' }, ...PARTIES.node_types],
      relationship_types: [{ label: 'LIVES_AT' }, ...PARTIES.relationship_types],
      patterns: [...PARTIES.patterns, ['Party', 'LIVES_AT', 'Address']],
    })

    expect(shortestPaths(map, 'VipCustomer', 'Address')).toEqual([
      {
        classes: ['VipCustomer', 'Address'],
        steps: [{ links: ['(Party)-[LIVES_AT]->(Address)'], ancestors: ['Customer', 'Party'] }],
      },
    ])
    // Ticket reaches Customer directly, or VipCustomer through Customer's Pattern, then
    // Address through Party's.
    expect(shortestPaths(map, 'Ticket', 'Address')).toEqual([
      {
        classes: ['Ticket', 'Customer', 'Address'],
        steps: [
          { links: ['(Customer)-[OPENED]->(Ticket)'], ancestors: [] },
          { links: ['(Party)-[LIVES_AT]->(Address)'], ancestors: ['Party'] },
        ],
      },
      {
        classes: ['Ticket', 'VipCustomer', 'Address'],
        steps: [
          { links: ['(Customer)-[OPENED]->(Ticket)'], ancestors: ['Customer'] },
          { links: ['(Party)-[LIVES_AT]->(Address)'], ancestors: ['Customer', 'Party'] },
        ],
      },
    ])
    // A superclass does not inherit its subclasses' Patterns: Party reaches Ticket only
    // the long way, back down through Address.
    expect(shortestPaths(map, 'Party', 'Ticket').map((p) => p.classes)).toEqual([
      ['Party', 'Address', 'Customer', 'Ticket'],
      ['Party', 'Address', 'VipCustomer', 'Ticket'],
    ])
  })

  it('keeps a path between two selected classes in focus, with the ancestors an inherited step climbs', () => {
    const map = ontologyMap({
      ...PARTIES,
      node_types: [...PARTIES.node_types, { label: 'Product' }],
      relationship_types: [...PARTIES.relationship_types, { label: 'ABOUT' }],
      patterns: [...PARTIES.patterns, ['Ticket', 'ABOUT', 'Product']],
    })

    expect(focusOf(map, { kind: 'path', from: 'VipCustomer', to: 'Product' })).toEqual({
      classes: new Set(['VipCustomer', 'Customer', 'Ticket', 'Product']),
      links: new Set(['(Customer)-[OPENED]->(Ticket)', '(Ticket)-[ABOUT]->(Product)']),
    })
    // With no path, only the two classes stay in focus.
    expect(focusOf(map, { kind: 'path', from: 'Party', to: 'Product' })).toEqual({
      classes: new Set(['Party', 'Product']),
      links: new Set(),
    })
    expect(focusOf(map, { kind: 'path', from: 'Party', to: 'Agent' })).toBeNull()
  })

  it('finds no path between classes nothing connects, nor to a class the Map does not have', () => {
    const map = ontologyMap({ ...ONTOLOGY, node_types: [...ONTOLOGY.node_types, { label: 'Agent' }] })

    expect(shortestPaths(map, 'Customer', 'Agent')).toEqual([])
    expect(shortestPaths(map, 'Customer', 'Invoice')).toEqual([])
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

  it('places a subclass nearer its superclass than any other class', async () => {
    // Bug's only tie is to its superclass Ticket.
    const positions = await layoutOntologyMap(ontologyMap(HIERARCHY))
    const distance = (p: Point, q: Point) => Math.hypot(p.x - q.x, p.y - q.y)
    const fromBug = Object.entries(positions)
      .filter(([label]) => label !== 'Bug')
      .sort(([, p], [, q]) => distance(positions.Bug, p) - distance(positions.Bug, q))

    expect(fromBug[0][0]).toBe('Ticket')
  })

  it('lays out the same hierarchy the same way every time', async () => {
    const first = await layoutOntologyMap(ontologyMap(HIERARCHY))
    const second = await layoutOntologyMap(ontologyMap(structuredClone(HIERARCHY)))

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
