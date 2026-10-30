import { describe, expect, it } from 'vitest'
import type { Ontology } from '@/api/ontology-versions'
import { ontologyMap } from './ontology-map'
import { layoutOntologyMap, NODE_SIZE, type Point } from './ontology-map-layout'
import { linkShape, type Box } from './ontology-map-links'
import { HIERARCHY, ONTOLOGY, PARTIES } from './ontology-map.fixtures'

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

  it.each([
    ['ONTOLOGY', ONTOLOGY],
    ['HIERARCHY', HIERARCHY],
    ['PARTIES', PARTIES],
    ['LONG_LABELS', LONG_LABELS],
  ])('leaves room for every link label clear of every class, in %s', async (_, ontology) => {
    const map = ontologyMap(ontology)
    const positions = await layoutOntologyMap(map)
    const nodes: Box[] = Object.values(positions).map((p) => ({ ...p, ...NODE_SIZE }))
    const overlap = (a: Box, b: Box) =>
      a.x < b.x + b.width && b.x < a.x + a.width && a.y < b.y + b.height && b.y < a.y + a.height

    const covered = map.links.filter((l) => {
      const { label } = linkShape(l, positions[l.source], positions[l.target])
      return nodes.some((n) => overlap(label, n))
    })
    expect(covered.map((l) => l.id)).toEqual([])
  })

  it('lays out an Ontology of 100 classes in under a second', async () => {
    const started = performance.now()
    await layoutOntologyMap(ontologyMap(generatedOntology(100)))

    expect(performance.now() - started).toBeLessThan(1000)
  })
})

/** Long relation names, parallel links and a self-loop, around Ticket. */
const LONG_LABELS: Ontology = {
  node_types: ['Agent', 'Customer', 'Product', 'Queue', 'Ticket'].map((label) => ({ label })),
  relationship_types: [
    'ASSIGNED_TO_QUEUE',
    'ESCALATED_BY_CUSTOMER',
    'FOLLOWS',
    'IS_DUPLICATE_OF',
    'OPENED',
    'REFERS_TO_PRODUCT',
  ].map((label) => ({ label })),
  patterns: [
    ['Agent', 'ASSIGNED_TO_QUEUE', 'Queue'],
    ['Customer', 'FOLLOWS', 'Ticket'],
    ['Customer', 'OPENED', 'Ticket'],
    ['Ticket', 'ASSIGNED_TO_QUEUE', 'Queue'],
    ['Ticket', 'ESCALATED_BY_CUSTOMER', 'Customer'],
    ['Ticket', 'IS_DUPLICATE_OF', 'Ticket'],
    ['Ticket', 'REFERS_TO_PRODUCT', 'Product'],
  ],
}

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
