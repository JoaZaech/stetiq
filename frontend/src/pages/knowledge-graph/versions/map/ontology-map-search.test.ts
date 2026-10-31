import { describe, expect, it } from 'vitest'
import type { Ontology } from '@/api/ontology-versions'
import { searchOntology } from './ontology-map-search'

// A slice of the retail-orders example: Bin mentions warehouses without being one.
const RETAIL: Ontology = {
  node_types: [
    {
      label: 'Bin',
      description: 'A storage location inside a Warehouse, added by the warehouse team',
      properties: [
        { name: 'code', type: 'STRING' },
        { name: 'warehouse', type: 'STRING' },
      ],
    },
    { label: 'Shipment' },
    { label: 'Warehouse', description: 'A fulfilment site shipments leave from' },
    { label: 'WarehouseZone' },
  ],
  relationship_types: [
    { label: 'SHIPPED_FROM', description: 'The warehouse a shipment left' },
    {
      label: 'STORED_IN',
      properties: [{ name: 'since', type: 'DATE', description: 'When it moved to the warehouse' }],
    },
  ],
  patterns: [
    ['Shipment', 'SHIPPED_FROM', 'Warehouse'],
    ['Bin', 'STORED_IN', 'Warehouse'],
  ],
}

describe('searchOntology', () => {
  it('lists name matches first, the exact name before names that only contain it', () => {
    expect(searchOntology(RETAIL, ' warehouse ').names).toEqual([
      { kind: 'class', label: 'Warehouse' },
      { kind: 'class', label: 'WarehouseZone' },
    ])
  })

  it('lists the other matches with each reason, quoting the description as written', () => {
    expect(searchOntology(RETAIL, 'Warehouse').others).toEqual([
      { kind: 'class', label: 'Bin', reasons: ["description mentions 'Warehouse'", 'attribute `warehouse`'] },
      { kind: 'relation', label: 'SHIPPED_FROM', reasons: ["description mentions 'warehouse'"] },
      { kind: 'relation', label: 'STORED_IN', reasons: ["attribute `since`: description mentions 'warehouse'"] },
    ])
  })

  it('matches relations by name, and a class by its description', () => {
    expect(searchOntology(RETAIL, 'shipment')).toEqual({
      names: [{ kind: 'class', label: 'Shipment' }],
      others: [
        { kind: 'class', label: 'Warehouse', reasons: ["description mentions 'shipment'"] },
        { kind: 'relation', label: 'SHIPPED_FROM', reasons: ["description mentions 'shipment'"] },
      ],
    })
    expect(searchOntology(RETAIL, 'shipped')).toEqual({
      names: [{ kind: 'relation', label: 'SHIPPED_FROM' }],
      others: [],
    })
  })

  it('finds nothing for an empty search', () => {
    expect(searchOntology(RETAIL, '  ')).toEqual({ names: [], others: [] })
  })
})
