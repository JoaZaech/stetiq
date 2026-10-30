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
        attributes: 1,
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

  it('counts each class’s own attributes and those it inherits along its superclass chain', () => {
    const { classes } = conceptTables(ONTOLOGY)

    expect(classes.map((c) => [c.label, c.attributes, c.inheritedAttributes])).toEqual([
      ['Person', 1, 0],
      ['Agent', 0, 1],
      ['Supervisor', 0, 1],
      ['Customer', 0, 1],
      ['Ticket', 1, 0],
    ])
  })

  it('counts a redeclared attribute once, as the class’s own',() => {
    const { classes } = conceptTables({
      node_types: [
        {
          label: 'Base',
          properties: [
            { name: 'id', type: 'STRING' },
            { name: 'name', type: 'STRING' },
          ],
        },
        { label: 'Sub', parent: 'Base', properties: [{ name: 'id', type: 'INTEGER' }] },
      ],
      relationship_types: [],
      patterns: [],
    })

    expect(classes.find((c) => c.label === 'Sub')).toMatchObject({ attributes: 1, inheritedAttributes: 1 })  })

  it('lists each class’s outgoing and incoming relations with the class at the other end', () => {
    const { classes } = conceptTables({
      node_types: [{ label: 'Paper' }, { label: 'Person' }],
      relationship_types: [{ label: 'CITES' }, { label: 'WROTE' }],
      patterns: [
        ['Paper', 'CITES', 'Paper'],
        ['Person', 'WROTE', 'Paper'],
      ],
    })

    expect(classes.map((c) => [c.label, c.outgoing, c.incoming])).toEqual([
      ['Paper', ['CITES → Paper'], ['CITES ← Paper', 'WROTE ← Person']],
      ['Person', ['WROTE → Paper'], []],
    ])
  })

  it('counts each relation’s attributes, keeping a relation without Patterns or attributes', () => {
    const { relations } = conceptTables({
      node_types: [{ label: 'Paper' }],
      relationship_types: [
        {
          label: 'CITES',
          properties: [
            { name: 'page', type: 'INTEGER' },
            { name: 'since', type: 'DATE' },
          ],
        },
        { label: 'UNUSED', deprecated: true },
      ],
      patterns: [['Paper', 'CITES', 'Paper']],
    })

    expect(relations.map((r) => [r.label, r.patterns, r.attributes, r.deprecated])).toEqual([
      ['CITES', ['(Paper)-[CITES]->(Paper)'], 2, false],
      ['UNUSED', [], 0, true],
    ])
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
