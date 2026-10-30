import { describe, expect, it } from 'vitest'
import { ontologyMap } from './ontology-map'
import type { Point } from './ontology-map-layout'
import { labelShown, linkShape, READABLE_ZOOM, type Box } from './ontology-map-links'
import { ONTOLOGY } from './ontology-map.fixtures'

const overlap = (a: Box, b: Box) =>
  a.x < b.x + b.width && b.x < a.x + a.width && a.y < b.y + b.height && b.y < a.y + a.height

describe('labelShown', () => {
  it('shows every link label at or above the readable zoom', () => {
    expect(labelShown(READABLE_ZOOM, { focused: false })).toBe(true)
    expect(labelShown(1.5, { focused: false, change: { kind: 'unchanged', severity: null } })).toBe(true)
  })

  it('below the readable zoom, shows only the labels of focused and changed links', () => {
    const zoom = READABLE_ZOOM / 2

    expect(labelShown(zoom, { focused: false })).toBe(false)
    expect(labelShown(zoom, { focused: false, change: { kind: 'unchanged', severity: null } })).toBe(false)
    expect(labelShown(zoom, { focused: true })).toBe(true)
    expect(labelShown(zoom, { focused: false, change: { kind: 'added', severity: 'additive' } })).toBe(true)
    expect(labelShown(zoom, { focused: false, change: { kind: 'removed', severity: 'breaking' } })).toBe(true)
    expect(labelShown(zoom, { focused: false, change: { kind: 'modified', severity: 'deprecating' } })).toBe(true)
  })
})

describe('linkShape', () => {
  // Three links between Customer and Ticket, one of them the other way round.
  const { links } = ontologyMap({
    ...ONTOLOGY,
    relationship_types: [...ONTOLOGY.relationship_types, { label: 'ESCALATED_BY' }],
    patterns: [...ONTOLOGY.patterns, ['Ticket', 'ESCALATED_BY', 'Customer']],
  })
  const parallel = links.filter((l) => [l.source, l.target].sort().join() === 'Customer,Ticket')

  it.each<[string, Point]>([
    ['side by side', { x: 400, y: 0 }],
    ['one above the other', { x: 0, y: 220 }],
    ['diagonally apart', { x: 260, y: 200 }],
  ])("staggers parallel links' labels so none overlaps another, %s", (_, ticket) => {
    const at: Record<string, Point> = { Customer: { x: 0, y: 0 }, Ticket: ticket }
    const labels = parallel.map((l) => linkShape(l, at[l.source], at[l.target]).label)

    expect(parallel).toHaveLength(3)
    for (const [i, a] of labels.entries()) {
      for (const b of labels.slice(i + 1)) expect(overlap(a, b)).toBe(false)
    }
  })
})
