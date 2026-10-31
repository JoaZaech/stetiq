import { describe, expect, it } from 'vitest'
import { ontologyMap } from './ontology-map'
import { shortestPaths } from './ontology-map-paths'
import { ONTOLOGY, PARTIES } from './ontology-map.fixtures'

describe('shortestPaths', () => {
  it('finds a direct path, through every Pattern joining its two classes, either way round', () => {
    const map = ontologyMap(ONTOLOGY)

    // Ticket to Customer runs against the links' direction: reachability is undirected.
    expect(shortestPaths(map, 'Ticket', 'Customer')).toEqual([
      {
        classes: ['Ticket', 'Customer'],
        steps: [{ links: ['(Customer)-[FOLLOWS]->(Ticket)', '(Customer)-[OPENED]->(Ticket)'], ancestors: [] }],
      },
    ])
  })

  it('finds every shortest path, and no longer one', () => {
    // Customer reaches Product through Order or through Ticket in two steps, and through
    // Ticket and Agent in three.
    const map = ontologyMap({
      node_types: [{ label: 'Agent' }, { label: 'Customer' }, { label: 'Order' }, { label: 'Product' }, { label: 'Ticket' }],
      relationship_types: [{ label: 'ABOUT' }, { label: 'ASSIGNED' }, { label: 'CONTAINS' }, { label: 'OPENED' }, { label: 'PLACED' }, { label: 'SUPPORTS' }],
      patterns: [
        ['Agent', 'SUPPORTS', 'Product'],
        ['Customer', 'OPENED', 'Ticket'],
        ['Customer', 'PLACED', 'Order'],
        ['Order', 'CONTAINS', 'Product'],
        ['Ticket', 'ABOUT', 'Product'],
        ['Ticket', 'ASSIGNED', 'Agent'],
      ],
    })

    expect(shortestPaths(map, 'Customer', 'Product')).toEqual([
      {
        classes: ['Customer', 'Order', 'Product'],
        steps: [
          { links: ['(Customer)-[PLACED]->(Order)'], ancestors: [] },
          { links: ['(Order)-[CONTAINS]->(Product)'], ancestors: [] },
        ],
      },
      {
        classes: ['Customer', 'Ticket', 'Product'],
        steps: [
          { links: ['(Customer)-[OPENED]->(Ticket)'], ancestors: [] },
          { links: ['(Ticket)-[ABOUT]->(Product)'], ancestors: [] },
        ],
      },
    ])
  })

  it("finds a path through a Pattern a class inherits, naming the ancestors it climbs to the Pattern's class", () => {
    // Party > Customer > VipCustomer, and only Party lives at an Address.
    const map = ontologyMap({
      ...PARTIES,
      node_types: [{ label: 'Address' }, ...PARTIES.node_types],
      relationship_types: [{ label: 'LIVES_AT' }, ...PARTIES.relationship_types],
      patterns: [...PARTIES.patterns, ['Party', 'LIVES_AT', 'Address']],
    })

    expect(shortestPaths(map, 'VipCustomer', 'Address')).toEqual([
      {
        classes: ['VipCustomer', 'Address'],
        steps: [{ links: ['(Party)-[LIVES_AT]->(Address)'], ancestors: ['Customer', 'Party'] }],
      },
    ])
    // Ticket reaches Customer directly, or VipCustomer through Customer's Pattern, then
    // Address through Party's.
    expect(shortestPaths(map, 'Ticket', 'Address')).toEqual([
      {
        classes: ['Ticket', 'Customer', 'Address'],
        steps: [
          { links: ['(Customer)-[OPENED]->(Ticket)'], ancestors: [] },
          { links: ['(Party)-[LIVES_AT]->(Address)'], ancestors: ['Party'] },
        ],
      },
      {
        classes: ['Ticket', 'VipCustomer', 'Address'],
        steps: [
          { links: ['(Customer)-[OPENED]->(Ticket)'], ancestors: ['Customer'] },
          { links: ['(Party)-[LIVES_AT]->(Address)'], ancestors: ['Customer', 'Party'] },
        ],
      },
    ])
    // A superclass does not inherit its subclasses' Patterns: Party reaches Ticket only
    // the long way, back down through Address.
    expect(shortestPaths(map, 'Party', 'Ticket').map((p) => p.classes)).toEqual([
      ['Party', 'Address', 'Customer', 'Ticket'],
      ['Party', 'Address', 'VipCustomer', 'Ticket'],
    ])
  })

  it('finds no path between classes nothing connects, nor to a class the Map does not have', () => {
    const map = ontologyMap({ ...ONTOLOGY, node_types: [...ONTOLOGY.node_types, { label: 'Agent' }] })

    expect(shortestPaths(map, 'Customer', 'Agent')).toEqual([])
    expect(shortestPaths(map, 'Customer', 'Invoice')).toEqual([])
  })
})
