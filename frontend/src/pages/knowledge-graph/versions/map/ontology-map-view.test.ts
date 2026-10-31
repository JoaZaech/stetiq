import { describe, expect, it, vi } from 'vitest'
import type { Ontology } from '@/api/ontology-versions'
import { compareOntologies } from '../comparison/ontology-map-comparison'
import { endpointChange } from '../comparison/ontology-diff.fixtures'
import type { ConceptSelection } from '../concept-selection'
import {
  canPick,
  createDrawMap,
  initialMapState,
  respondTo,
  type MapGesture,
  type DrawnMap,
  type MapInput,
} from './ontology-map-view'
import { HIERARCHY, ONTOLOGY, PARTIES } from './ontology-map.fixtures'
import { shortestPaths } from './ontology-map-paths'
import { searchOntology } from './ontology-map-search'

// Counted, to check each runs only when what it reads changes.
vi.mock('./ontology-map-paths', async (actual) => {
  const paths = await actual<typeof import('./ontology-map-paths')>()
  return { ...paths, shortestPaths: vi.fn(paths.shortestPaths) }
})
vi.mock('./ontology-map-search', async (actual) => {
  const search = await actual<typeof import('./ontology-map-search')>()
  return { ...search, searchOntology: vi.fn(search.searchOntology) }
})

/** The Map of `ontology` opened on `selected` (a `?select=`), as `OntologyMap` opens it. */
function open(ontology: Ontology, selected: ConceptSelection | null, query = '') {
  return createDrawMap()({ ontology, selected, query }, initialMapState(selected))
}

// OPENED gained Customer → Ticket; Agent → Ticket is unchanged and comes first.
const BASE: Ontology = {
  node_types: [{ label: 'Agent' }, { label: 'Customer' }, { label: 'Ticket' }],
  relationship_types: [{ label: 'OPENED' }],
  patterns: [['Agent', 'OPENED', 'Ticket']],
}
const OPENED_BY_CUSTOMER = endpointChange(['Customer', 'OPENED', 'Ticket'], 'added')
const COMPARISON = compareOntologies(
  BASE,
  { ...BASE, patterns: [...BASE.patterns, ['Customer', 'OPENED', 'Ticket']] },
  { classification: 'additive', changes: [OPENED_BY_CUSTOMER] },
)

/** The comparison's Map opened on `selected`. */
function compare(selected: ConceptSelection | null) {
  return createDrawMap()({ comparison: COMPARISON, selected, query: '' }, initialMapState(selected))
}

/** The Map after the user's `gestures`, each answered as `OntologyMap` answers it. */
function after(view: DrawnMap, ...gestures: MapGesture[]): DrawnMap {
  const drawMap = createDrawMap()
  for (const g of gestures) {
    const { state, select } = respondTo(view, g)
    const input: MapInput = { ...view.input, selected: select === undefined ? view.input.selected : select }
    view = drawMap(input, state)
  }
  return view
}

describe('drawMap', () => {
  it('emphasizes a selected class and its neighbourhood, and fades the rest', () => {
    // Customer links to Ticket only; Product is two steps away.
    const view = open(ONTOLOGY, { kind: 'class', label: 'Customer' })

    expect(view.selection).toEqual({ kind: 'class', label: 'Customer' })
    expect(view.classes).toEqual({
      Customer: { selected: true, match: false, faded: false },
      Ticket: { selected: false, match: false, faded: false },
      Product: { selected: false, match: false, faded: true },
    })
    expect(view.links['(Customer)-[OPENED]->(Ticket)']).toEqual({
      selected: false,
      match: false,
      faded: false,
      focused: true,
    })
    expect(view.links['(Ticket)-[ABOUT]->(Product)']).toEqual({
      selected: false,
      match: false,
      faded: true,
      focused: false,
    })
  })

  describe('a relation', () => {
    // ESCALATED's first link is to the deprecated Archive, then to Ticket.
    const ESCALATED: Ontology = {
      node_types: [{ label: 'Archive', deprecated: true }, { label: 'Customer' }, { label: 'Ticket' }],
      relationship_types: [{ label: 'ESCALATED' }],
      patterns: [
        ['Customer', 'ESCALATED', 'Archive'],
        ['Customer', 'ESCALATED', 'Ticket'],
      ],
    }

    it('selects its first shown link', () => {
      const view = open(ESCALATED, { kind: 'relation', label: 'ESCALATED' })

      expect(view.selection).toEqual({ kind: 'link', id: '(Customer)-[ESCALATED]->(Archive)' })
      expect(after(view, { kind: 'filter', filters: { hideDeprecated: true } }).selection).toEqual({
        kind: 'link',
        id: '(Customer)-[ESCALATED]->(Ticket)',
      })
    })

    it('selects nothing when a filter hides every link of it', () => {
      const view = after(open(HIERARCHY, { kind: 'relation', label: 'FILED' }), {
        kind: 'filter',
        filters: { hideDeprecated: true },
      })

      expect(view.selection).toBeNull()
      expect(view.focus).toBeNull()
      expect(view.details).toBeNull()
    })

    it('in a comparison, selects its first shown changed link', () => {
      expect(compare({ kind: 'relation', label: 'OPENED' }).selection).toEqual({
        kind: 'link',
        id: '(Customer)-[OPENED]->(Ticket)',
      })
    })
  })

  it("lists a comparison's changes behind the selection, and none outside a comparison", () => {
    expect(compare({ kind: 'link', id: '(Customer)-[OPENED]->(Ticket)' }).changes).toEqual([OPENED_BY_CUSTOMER])
    expect(compare({ kind: 'class', label: 'Agent' }).changes).toEqual([])
    expect(open(ONTOLOGY, { kind: 'class', label: 'Ticket' }).changes).toBeNull()
  })

  describe('clicking', () => {
    const customer = open(ONTOLOGY, { kind: 'class', label: 'Customer' })

    it('selects the class or Pattern link clicked', () => {
      expect(after(customer, { kind: 'click-class', label: 'Product', shift: false }).input.selected).toEqual({
        kind: 'class',
        label: 'Product',
      })
      expect(after(customer, { kind: 'click-link', id: '(Ticket)-[ABOUT]->(Product)' }).selection).toEqual({
        kind: 'link',
        id: '(Ticket)-[ABOUT]->(Product)',
      })
    })

    it('asks for the shortest paths to a second class when shift-clicking it', () => {
      const view = after(customer, { kind: 'click-class', label: 'Product', shift: true })

      expect(view.selection).toEqual({ kind: 'path', from: 'Customer', to: 'Product' })
      // Customer → Ticket → Product, by either of Customer's two links to Ticket.
      expect(view.paths?.map((p) => p.classes)).toEqual([['Customer', 'Ticket', 'Product']])
      // The path's two classes and every link along it are selected; the rest fades.
      expect(view.classes.Customer.selected && view.classes.Product.selected).toBe(true)
      expect(view.classes.Ticket).toEqual({ selected: false, match: false, faded: false })
      expect(Object.keys(view.links).filter((id) => view.links[id].selected)).toEqual([
        '(Customer)-[FOLLOWS]->(Ticket)',
        '(Customer)-[OPENED]->(Ticket)',
        '(Ticket)-[ABOUT]->(Product)',
      ])
      expect(view.links['(Ticket)-[DUPLICATES]->(Ticket)'].faded).toBe(true)
    })

    it('selects just the class when shift-clicking with no class selected, or the selected one', () => {
      const shiftClick = { kind: 'click-class', label: 'Customer', shift: true } as const

      expect(after(customer, shiftClick).selection).toEqual({ kind: 'class', label: 'Customer' })
      expect(after(open(ONTOLOGY, null), shiftClick).selection).toEqual({ kind: 'class', label: 'Customer' })
    })
  })

  describe('the Concept search', () => {
    it('matches what it names and, with nothing selected, fades the rest', () => {
      // "open" names OPENED, and is only in Customer's description.
      const view = open(PARTIES, null, 'open')

      expect(view.results.names).toEqual([{ kind: 'relation', label: 'OPENED' }])
      expect(view.results.others.map((r) => r.label)).toEqual(['Customer'])
      expect(view.links['(Customer)-[OPENED]->(Ticket)']).toEqual({
        selected: false,
        match: true,
        faded: false,
        focused: false,
      })
      expect(view.classes.Customer).toEqual({ selected: false, match: false, faded: true })
    })

    it('leaves fading to the selection when there is one', () => {
      const view = open(PARTIES, { kind: 'class', label: 'Customer' }, 'open')

      expect(view.classes.Customer).toEqual({ selected: true, match: false, faded: false })
      expect(view.links['(Customer)-[OPENED]->(Ticket)'].match).toBe(true)
    })
  })

  it('fades a subclass link with either of its classes', () => {
    // Ticket's neighbourhood is Customer alone; its subclasses fade, and their links with them.
    const view = open(HIERARCHY, { kind: 'class', label: 'Incident' })

    expect(view.subclassLinks).toEqual({
      'Bug -> Ticket': { faded: true },
      'Incident -> Ticket': { faded: true },
      'LegacyTicket -> Ticket': { faded: true },
    })
    expect(view.classes.Customer.faded).toBe(false)
  })

  it('shows the focus of what the change summary previews, without selecting it', () => {
    const view = after(open(ONTOLOGY, { kind: 'class', label: 'Customer' }), {
      kind: 'preview',
      selection: { kind: 'class', label: 'Product' },
    })

    expect(view.selection).toEqual({ kind: 'class', label: 'Customer' })
    expect(view.focus?.classes).toEqual(new Set(['Product', 'Ticket']))
    expect(view.classes.Customer.faded).toBe(true)
    expect(view.details).toMatchObject({ kind: 'class', label: 'Customer' })
  })

  describe('centring', () => {
    it('opens centred on the selection, a relation on its link, and fits the view with none', () => {
      expect(open(ONTOLOGY, { kind: 'class', label: 'Ticket' })).toMatchObject({
        centreOn: { kind: 'class', label: 'Ticket' },
        fitView: false,
      })
      expect(open(ONTOLOGY, { kind: 'relation', label: 'ABOUT' }).centreOn).toEqual({
        kind: 'link',
        id: '(Ticket)-[ABOUT]->(Product)',
      })
      expect(open(ONTOLOGY, null)).toMatchObject({ centreOn: null, fitView: true })
    })

    it('lets go once something else is selected on the Map', () => {
      const view = after(open(ONTOLOGY, { kind: 'class', label: 'Ticket' }), {
        kind: 'click-class',
        label: 'Customer',
        shift: false,
      })

      expect(view.centreOn).toBeNull()
      // Back on the class it opened on, it centres again.
      expect(after(view, { kind: 'click-class', label: 'Ticket', shift: false }).centreOn).toEqual({
        kind: 'class',
        label: 'Ticket',
      })
    })

    it('centres on a search result picked, which selects it', () => {
      const view = after(open(ONTOLOGY, null, 'o'), { kind: 'pick', result: { kind: 'relation', label: 'OPENED' } })

      expect(view.input.selected).toEqual({ kind: 'relation', label: 'OPENED' })
      expect(view.centreOn).toEqual({ kind: 'link', id: '(Customer)-[OPENED]->(Ticket)' })
    })
  })

  it('can pick only a search result that is shown', () => {
    const view = after(open(HIERARCHY, null, 'e'), { kind: 'filter', filters: { hideDeprecated: true } })

    expect(canPick(view, { kind: 'class', label: 'Incident' })).toBe(true)
    expect(canPick(view, { kind: 'class', label: 'LegacyTicket' })).toBe(false)
    expect(canPick(view, { kind: 'relation', label: 'REPORTED' })).toBe(true)
    expect(canPick(view, { kind: 'relation', label: 'FILED' })).toBe(false)
  })

  describe('clearing', () => {
    // Opened on a deprecated relation, then hidden: selected on the page, but not on the Map.
    const hidden = after(open(HIERARCHY, { kind: 'relation', label: 'FILED' }), {
      kind: 'filter',
      filters: { hideDeprecated: true },
    })

    it('clicking the background or closing a panel clears the page selection', () => {
      expect(respondTo(open(ONTOLOGY, { kind: 'class', label: 'Ticket' }), { kind: 'clear' }).select).toBeNull()
      expect(respondTo(hidden, { kind: 'clear' }).select).toBeNull()
    })

    it('Escape clears only a selection the Map shows', () => {
      expect(respondTo(open(ONTOLOGY, { kind: 'class', label: 'Ticket' }), { kind: 'escape' }).select).toBeNull()
      expect(respondTo(hidden, { kind: 'escape' })).not.toHaveProperty('select')
    })
  })

  it('selects what the change summary selects, without centring on it', () => {
    const view = after(open(ONTOLOGY, null), { kind: 'select', concept: { kind: 'class', label: 'Ticket' } })

    expect(view.selection).toEqual({ kind: 'class', label: 'Ticket' })
    expect(view.centreOn).toBeNull()
  })

  it('finds paths and searches once per change of what they read', () => {
    vi.mocked(shortestPaths).mockClear()
    vi.mocked(searchOntology).mockClear()
    const drawMap = createDrawMap()
    const path = { kind: 'path', from: 'Customer', to: 'Product' } as const
    const state = initialMapState(path)
    const input = { ontology: ONTOLOGY, selected: path, query: 'ticket' }

    drawMap(input, state)
    // The same `?select=` as a new object, a preview and another search: no new paths.
    drawMap({ ...input, selected: { ...path } }, state)
    drawMap({ ...input, query: 'product' }, { ...state, preview: { kind: 'class', label: 'Ticket' } })
    expect(shortestPaths).toHaveBeenCalledTimes(1)
    expect(searchOntology).toHaveBeenCalledTimes(2)

    // Another selection: no new search.
    drawMap({ ...input, query: 'product', selected: { kind: 'path', from: 'Product', to: 'Customer' } }, state)
    expect(shortestPaths).toHaveBeenCalledTimes(2)
    expect(searchOntology).toHaveBeenCalledTimes(2)
  })

  it('still finds paths through inherited Patterns with subclass links hidden', () => {
    // VipCustomer reaches Ticket through the OPENED Pattern it inherits from Customer.
    const view = after(open(PARTIES, { kind: 'path', from: 'VipCustomer', to: 'Ticket' }), {
      kind: 'filter',
      filters: { hideSubclassLinks: true },
    })

    expect(view.shown.subclassLinks).toEqual([])
    expect(view.paths?.map((p) => p.classes)).toEqual([['VipCustomer', 'Ticket']])
    expect(view.classes.Customer.faded).toBe(false)
    expect(view.classes.Party.faded).toBe(true)
  })

  it('selects nothing that a filter hides', () => {
    const view = after(open(HIERARCHY, { kind: 'path', from: 'Customer', to: 'LegacyTicket' }), {
      kind: 'filter',
      filters: { hideDeprecated: true },
    })

    expect(view.paths).toBeNull()
    expect(view.focus).toBeNull()
    expect(Object.values(view.classes).some((c) => c.faded)).toBe(false)
  })
})
