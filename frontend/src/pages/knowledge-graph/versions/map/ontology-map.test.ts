import { describe, expect, it } from 'vitest'
import { filterOntologyMap, ontologyMap } from './ontology-map'
import { HIERARCHY, ONTOLOGY } from './ontology-map.fixtures'

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
