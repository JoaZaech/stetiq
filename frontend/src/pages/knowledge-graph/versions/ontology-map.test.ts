import { describe, expect, it } from 'vitest'
import type { Ontology } from '@/api/ontology-versions'
import { layoutOntologyMap, NODE_SIZE, ontologyMap, type Point } from './ontology-map'

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
