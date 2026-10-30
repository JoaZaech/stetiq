import { describe, expect, it } from 'vitest'
import type { Ontology } from '@/api/ontology-versions'
import { attributeRows } from './attribute-rows'

// Canonical form, as the server sends it: Concepts sorted by label.
const ONTOLOGY: Ontology = {
  node_types: [
    { label: 'Agent', parent: 'Person' },
    {
      label: 'Customer',
      parent: 'Person',
      properties: [{ name: 'email', type: 'STRING', description: 'Where we write to' }],
    },
    { label: 'Person', properties: [{ name: 'name', type: 'STRING', required: true }] },
    { label: 'Supervisor', parent: 'Agent' },
  ],
  relationship_types: [{ label: 'KNOWS', properties: [{ name: 'since', type: 'DATE' }] }],
  patterns: [['Customer', 'KNOWS', 'Agent']],
  constraints: [
    { type: 'UNIQUENESS', node_type: 'Customer', property_name: 'name' },
    { type: 'UNIQUENESS', node_type: 'Customer', property_name: 'email' },
  ],
}

describe('attributeRows', () => {
  it('lists each class’s own attributes, then those it inherits marked with the declaring ancestor, then relations’', () => {
    expect(attributeRows(ONTOLOGY).map((a) => [a.owner, a.ownerKind, a.name, a.inheritedFrom])).toEqual([
      ['Person', 'class', 'name', undefined],
      ['Agent', 'class', 'name', 'Person'],
      ['Supervisor', 'class', 'name', 'Person'],
      ['Customer', 'class', 'email', undefined],
      ['Customer', 'class', 'name', 'Person'],
      ['KNOWS', 'relation', 'since', undefined],
    ])
  })

  it('carries type, required, description and the owner’s superclass', () => {
    const rows = attributeRows(ONTOLOGY)

    expect(rows.find((a) => a.owner === 'Supervisor')).toEqual({
      id: 'Supervisor.name',
      owner: 'Supervisor',
      ownerKind: 'class',
      ownerParent: 'Agent',
      name: 'name',
      type: 'STRING',
      required: true,
      unique: false,
      inheritedFrom: 'Person',
      description: undefined,
    })
    expect(rows.find((a) => a.name === 'email')).toMatchObject({ required: false, description: 'Where we write to' })
  })

  it('marks an attribute unique where a uniqueness constraint covers it on that class', () => {
    const unique = attributeRows(ONTOLOGY)
      .filter((a) => a.unique)
      .map((a) => a.id)

    expect(unique).toEqual(['Customer.email', 'Customer.name'])
  })
})
