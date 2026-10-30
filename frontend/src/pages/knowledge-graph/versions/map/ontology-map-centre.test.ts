import { describe, expect, it } from 'vitest'
import { ontologyMap } from './ontology-map'
import { centreOf, locatedSelection } from './ontology-map-centre'
import { ONTOLOGY } from './ontology-map.fixtures'

// Classes are 160 × 40 unless sized otherwise.
const map = ontologyMap(ONTOLOGY)
const positions = { Customer: { x: 0, y: 0 }, Product: { x: 400, y: 0 }, Ticket: { x: 200, y: 200 } }

describe('centreOf', () => {
  it('centres on a class, at its own size', () => {
    expect(centreOf(map, positions, {}, { kind: 'class', label: 'Customer' })).toEqual({ x: 80, y: 20 })
    expect(
      centreOf(map, positions, { Customer: { width: 300, height: 100 } }, { kind: 'class', label: 'Customer' }),
    ).toEqual({ x: 150, y: 50 })
  })

  it('centres on a link halfway between its two classes', () => {
    expect(centreOf(map, positions, {}, { kind: 'link', id: '(Ticket)-[ABOUT]->(Product)' })).toEqual({
      x: 380,
      y: 120,
    })
  })

  it('centres on nothing for a path, no selection, or what the Map lacks', () => {
    expect(centreOf(map, positions, {}, { kind: 'path', from: 'Customer', to: 'Product' })).toBeNull()
    expect(centreOf(map, positions, {}, null)).toBeNull()
    expect(centreOf(map, positions, {}, { kind: 'class', label: 'Agent' })).toBeNull()
    expect(centreOf(map, positions, {}, { kind: 'link', id: '(A)-[X]->(B)' })).toBeNull()
  })
})

describe('locatedSelection', () => {
  const link = { kind: 'link', id: '(Customer)-[OPENED]->(Ticket)' } as const

  it('keeps the Map on the selection it was located on', () => {
    expect(locatedSelection('class:Ticket', { kind: 'class', label: 'Ticket' }, { kind: 'class', label: 'Ticket' }))
      .toEqual({ kind: 'class', label: 'Ticket' })
    // A relation is located on the Map as one of its links.
    expect(locatedSelection('relation:OPENED', { kind: 'relation', label: 'OPENED' }, link)).toEqual(link)
  })

  it('lets go once something else is selected, or nothing was located', () => {
    expect(locatedSelection('class:Ticket', { kind: 'class', label: 'Customer' }, { kind: 'class', label: 'Customer' }))
      .toBeNull()
    expect(locatedSelection(null, { kind: 'class', label: 'Ticket' }, { kind: 'class', label: 'Ticket' })).toBeNull()
    expect(locatedSelection('class:Ticket', null, null)).toBeNull()
  })
})
