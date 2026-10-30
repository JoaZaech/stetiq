import { describe, expect, it } from 'vitest'
import type { Ontology } from '@/api/ontology-versions'
import { ontologyMap } from './ontology-map'
import { layoutOntologyMap, NODE_SIZE, type Point } from './ontology-map-layout'
import { HIERARCHY, ONTOLOGY } from './ontology-map.fixtures'

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
