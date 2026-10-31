/** Ontologies the Ontology Map's tests share. */
import type { Ontology } from '@/api/ontology-versions'
import { compareOntologies } from '../comparison/ontology-map-comparison'
import { attributeChange, conceptDescribed } from '../comparison/ontology-diff.fixtures'

// Canonical form, as the server sends it: Concepts sorted by label.
export const ONTOLOGY: Ontology = {
  node_types: [{ label: 'Customer' }, { label: 'Product' }, { label: 'Ticket' }],
  relationship_types: [{ label: 'ABOUT' }, { label: 'DUPLICATES' }, { label: 'FOLLOWS' }, { label: 'OPENED' }],
  patterns: [
    ['Customer', 'FOLLOWS', 'Ticket'],
    ['Customer', 'OPENED', 'Ticket'],
    ['Ticket', 'ABOUT', 'Product'],
    ['Ticket', 'DUPLICATES', 'Ticket'],
  ],
}

// A class hierarchy, Party > Customer > VipCustomer, with properties at each level.
export const PARTIES: Ontology = {
  node_types: [
    {
      label: 'Customer',
      description: 'Someone who opens tickets',
      parent: 'Party',
      properties: [{ name: 'email', type: 'STRING' }],
    },
    { label: 'Party', properties: [{ name: 'name', type: 'STRING', required: true }] },
    { label: 'Ticket' },
    { label: 'VipCustomer', parent: 'Customer', properties: [{ name: 'tier', type: 'INTEGER', description: '1 to 3' }] },
  ],
  relationship_types: [
    {
      label: 'OPENED',
      description: 'The customer opened the ticket',
      properties: [{ name: 'at', type: 'DATE_TIME', required: true }],
    },
  ],
  patterns: [['Customer', 'OPENED', 'Ticket']],
  constraints: [
    { type: 'UNIQUENESS', node_type: 'VipCustomer', property_name: 'tier' },
    { type: 'UNIQUENESS', node_type: 'Party', property_name: 'name' },
  ],
}

// A hierarchy under Ticket, with a deprecated class and a deprecated relation.
export const HIERARCHY: Ontology = {
  node_types: [
    { label: 'Bug', parent: 'Ticket' },
    { label: 'Customer' },
    { label: 'Incident', parent: 'Ticket' },
    { label: 'LegacyTicket', parent: 'Ticket', deprecated: true },
    { label: 'Ticket' },
  ],
  relationship_types: [{ label: 'FILED', deprecated: true }, { label: 'OPENED' }, { label: 'REPORTED' }],
  patterns: [
    ['Customer', 'FILED', 'Ticket'],
    ['Customer', 'OPENED', 'Ticket'],
    ['Customer', 'REPORTED', 'Incident'],
    ['Customer', 'REPORTED', 'LegacyTicket'],
  ],
}

// City transit, as the `ontology_map_transit` seed has it: v3 renames Stop's and Trip's
// attributes (each a breaking removal and an additive addition) and documents HAS_TRIP.
const TRANSIT_V2: Ontology = {
  node_types: [
    { label: 'Agency' },
    { label: 'Route' },
    { label: 'Stop', properties: [{ name: 'wheelchairBoarding', type: 'INTEGER' }] },
    { label: 'Trip', properties: [{ name: 'bikesAllowed', type: 'INTEGER' }] },
  ],
  relationship_types: [{ label: 'HAS_TRIP' }, { label: 'OPERATES' }, { label: 'SERVES' }],
  patterns: [
    ['Agency', 'OPERATES', 'Route'],
    ['Route', 'HAS_TRIP', 'Trip'],
    ['Trip', 'SERVES', 'Stop'],
  ],
}
const TRANSIT_V3: Ontology = {
  ...TRANSIT_V2,
  node_types: [
    { label: 'Agency' },
    { label: 'Route' },
    { label: 'Stop', properties: [{ name: 'wheelchair_boarding', type: 'INTEGER' }] },
    { label: 'Trip', properties: [{ name: 'bikes_allowed', type: 'INTEGER' }] },
  ],
  relationship_types: [
    { label: 'HAS_TRIP', description: 'The scheduled trips of a route' },
    { label: 'OPERATES' },
    { label: 'SERVES' },
  ],
}
export const TRANSIT = compareOntologies(TRANSIT_V2, TRANSIT_V3, {
  classification: 'breaking',
  changes: [
    attributeChange('node_type', 'Stop', 'wheelchairBoarding', 'removed', 'breaking'),
    attributeChange('node_type', 'Stop', 'wheelchair_boarding', 'added', 'additive'),
    attributeChange('node_type', 'Trip', 'bikesAllowed', 'removed', 'breaking'),
    attributeChange('node_type', 'Trip', 'bikes_allowed', 'added', 'additive'),
    conceptDescribed('relationship_type', 'HAS_TRIP'),
  ],
})
