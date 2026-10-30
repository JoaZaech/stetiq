import { describe, expect, it } from 'vitest'
import type { Ontology } from '@/api/ontology-versions'
import { ontologyMap } from './ontology-map'

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
