import { describe, expect, it } from 'vitest'
import type { Ontology } from '@/api/ontology-versions'
import { ontologyMap } from './ontology-map'
import {
  changedOf,
  contextOf,
  detailsOf,
  focusOf,
  neighboursOf,
  relationSelection,
  searchMap,
} from './ontology-map-focus'
import { searchOntology } from './ontology-map-search'
import { HIERARCHY, ONTOLOGY, PARTIES, TRANSIT } from './ontology-map.fixtures'

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
})

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
  const search = (query: string) => searchMap(ontologyMap(PARTIES), query, searchOntology(PARTIES, query))

  it('matches the classes and links the search names, not those it only mentions', () => {
    // "open" names the OPENED relation and is only in Customer's description.
    expect(search(' OPEN ')).toEqual({
      classes: new Set(),
      links: new Set(['(Customer)-[OPENED]->(Ticket)']),
    })
    expect(search('customer')).toEqual({ classes: new Set(['Customer', 'VipCustomer']), links: new Set() })
    // "tier" is only a VipCustomer attribute.
    expect(search('tier')).toEqual({ classes: new Set(), links: new Set() })
  })

  it('matches nothing in particular for an empty search', () => {
    expect(search('  ')).toBeNull()
  })
})

describe('relationSelection', () => {
  // REPORTED has two links: to Incident, then to LegacyTicket.
  const { links } = ontologyMap(HIERARCHY)

  it('stands a relation for its first link the preference picks', () => {
    const toLegacy = (l: { target: string }) => l.target === 'LegacyTicket'

    expect(relationSelection(links, 'REPORTED', toLegacy)).toEqual({
      kind: 'link',
      id: '(Customer)-[REPORTED]->(LegacyTicket)',
    })
  })

  it('falls back to its first link when the preference picks none', () => {
    expect(relationSelection(links, 'REPORTED', () => false)).toEqual({
      kind: 'link',
      id: '(Customer)-[REPORTED]->(Incident)',
    })
  })

  it('stands for nothing when none of the links is the relation’s', () => {
    expect(relationSelection(links, 'UNKNOWN', () => true)).toBeNull()
    expect(relationSelection([], 'REPORTED', () => true)).toBeNull()
  })
})

describe('contextOf', () => {
  it('keeps the changed items out of focus as context, so only the unchanged ones fade', () => {
    const focus = focusOf(TRANSIT.map, { kind: 'link', id: '(Agency)-[OPERATES]->(Route)' })!

    // Trip and Stop broke, and HAS_TRIP is documentation-only; SERVES did not change.
    expect(contextOf(focus, changedOf(TRANSIT))).toEqual({
      classes: new Set(['Stop', 'Trip']),
      links: new Set(['(Route)-[HAS_TRIP]->(Trip)']),
    })
  })

  it('leaves out what is in focus', () => {
    const focus = focusOf(TRANSIT.map, { kind: 'class', label: 'Trip' })!

    expect(contextOf(focus, changedOf(TRANSIT))).toEqual({ classes: new Set(), links: new Set() })
  })
})
