import { describe, expect, it } from 'vitest'
import type { Ontology } from '@/api/ontology-versions'
import { conceptTables, searchConcepts } from './concepts'

// Canonical form, as the server sends it: Concepts sorted by label.
const ONTOLOGY: Ontology = {
  node_types: [
    { label: 'Agent', parent: 'Person' },
    { label: 'Customer', parent: 'Person', description: 'Someone who opens tickets' },
    { label: 'Person', properties: [{ name: 'name', type: 'STRING', required: true }] },
    { label: 'Supervisor', parent: 'Agent' },
    { label: 'Ticket', properties: [{ name: 'opened_at', type: 'DATE' }] },
  ],
  relationship_types: [{ label: 'OPENED', properties: [{ name: 'via', type: 'STRING' }] }],
  patterns: [
    ['Customer', 'OPENED', 'Ticket'],
    ['Agent', 'OPENED', 'Ticket'],
  ],
  constraints: [{ type: 'UNIQUENESS', node_type: 'Customer', property_name: 'name' }],
}

describe('conceptTables', () => {
  it('orders classes depth-first under their superclass', () => {
    const { classes } = conceptTables(ONTOLOGY)

    expect(classes.map((c) => [c.label, c.depth, c.parent])).toEqual([
      ['Person', 0, undefined],
      ['Agent', 1, 'Person'],
      ['Supervisor', 2, 'Agent'],
      ['Customer', 1, 'Person'],
      ['Ticket', 0, undefined],
    ])
  })

  it('lists constraints on the class they constrain', () => {
    const { classes } = conceptTables(ONTOLOGY)

    expect(classes.find((c) => c.label === 'Customer')?.constraints).toEqual(['UNIQUENESS (name)'])
    expect(classes.find((c) => c.label === 'Person')?.constraints).toEqual([])
  })

  it('lists relations with their patterns, and attributes with their owner', () => {
    const { relations, attributes } = conceptTables(ONTOLOGY)

    expect(relations).toEqual([
      {
        label: 'OPENED',
        description: undefined,
        deprecated: false,
        patterns: ['(Agent)-[OPENED]->(Ticket)', '(Customer)-[OPENED]->(Ticket)'],
      },
    ])
    expect(attributes.map((a) => [a.owner, a.name, a.type, a.required])).toEqual([
      ['Person', 'name', 'STRING', true],
      ['Ticket', 'opened_at', 'DATE', false],
      ['OPENED', 'via', 'STRING', false],
    ])
  })

  it('keeps a class whose superclass is missing at the top level', () => {
    const { classes } = conceptTables({
      node_types: [{ label: 'Orphan', parent: 'Gone' }],
      relationship_types: [],
      patterns: [],
    })

    expect(classes.map((c) => [c.label, c.depth])).toEqual([['Orphan', 0]])
  })
})

describe('searchConcepts', () => {
  it('keeps Concepts whose name or description contains the query, ignoring case', () => {
    const found = searchConcepts(conceptTables(ONTOLOGY), 'TICKETS')

    expect(found.classes.map((c) => c.label)).toEqual(['Customer'])
    expect(found.relations).toEqual([])
    expect(found.attributes).toEqual([])
  })

  it('matches attributes by their owner too', () => {
    const found = searchConcepts(conceptTables(ONTOLOGY), 'ticket')

    expect(found.classes.map((c) => c.label)).toEqual(['Customer', 'Ticket'])
    expect(found.attributes.map((a) => `${a.owner}.${a.name}`)).toEqual(['Ticket.opened_at'])
  })

  it('returns everything for a blank query', () => {
    const tables = conceptTables(ONTOLOGY)

    expect(searchConcepts(tables, '  ')).toBe(tables)
  })
})
