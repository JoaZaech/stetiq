import { describe, expect, it } from 'vitest'
import { formatSelection, parseSelection, selectedRows } from './concept-selection'
import { ONTOLOGY } from './map/ontology-map.fixtures'

describe('parseSelection', () => {
  it('reads a class, a relation, a link and a path', () => {
    expect(parseSelection('class:Trip')).toEqual({ kind: 'class', label: 'Trip' })
    expect(parseSelection('relation:HAS_TRIP')).toEqual({ kind: 'relation', label: 'HAS_TRIP' })
    expect(parseSelection('link:(Route)-[HAS_TRIP]->(Trip)')).toEqual({
      kind: 'link',
      id: '(Route)-[HAS_TRIP]->(Trip)',
    })
    expect(parseSelection('path:Customer->Product')).toEqual({ kind: 'path', from: 'Customer', to: 'Product' })
  })

  it('reads nothing from an absent, empty or unknown value', () => {
    expect(parseSelection(null)).toBeNull()
    expect(parseSelection('')).toBeNull()
    expect(parseSelection('class:')).toBeNull()
    expect(parseSelection('Trip')).toBeNull()
    expect(parseSelection('attribute:Trip.id')).toBeNull()
    expect(parseSelection('path:Customer')).toBeNull()
  })
})

describe('formatSelection', () => {
  it('writes each kind as its prefix and name', () => {
    expect(formatSelection({ kind: 'class', label: 'Trip' })).toBe('class:Trip')
    expect(formatSelection({ kind: 'relation', label: 'HAS_TRIP' })).toBe('relation:HAS_TRIP')
    expect(formatSelection({ kind: 'link', id: '(Route)-[HAS_TRIP]->(Trip)' })).toBe(
      'link:(Route)-[HAS_TRIP]->(Trip)',
    )
    expect(formatSelection({ kind: 'path', from: 'Customer', to: 'Product' })).toBe('path:Customer->Product')
  })
})

describe('selectedRows', () => {
  it('highlights the class or relation selected, a link’s relation, and both ends of a path', () => {
    const rows = (value: string) => {
      const { classes, relations } = selectedRows(ONTOLOGY, parseSelection(value))
      return { classes: [...classes], relations: [...relations] }
    }
    expect(rows('class:Ticket')).toEqual({ classes: ['Ticket'], relations: [] })
    expect(rows('relation:OPENED')).toEqual({ classes: [], relations: ['OPENED'] })
    expect(rows('link:(Customer)-[OPENED]->(Ticket)')).toEqual({ classes: [], relations: ['OPENED'] })
    expect(rows('path:Customer->Product')).toEqual({ classes: ['Customer', 'Product'], relations: [] })
  })

  it('highlights nothing for no selection or a link the Ontology lacks', () => {
    expect(selectedRows(ONTOLOGY, null)).toEqual({ classes: new Set(), relations: new Set() })
    expect(selectedRows(ONTOLOGY, parseSelection('link:(A)-[X]->(B)')).relations.size).toBe(0)
  })
})
