/** Where each class of the Map goes: a seeded ELK stress layout. */
import ELK from 'elkjs/lib/elk.bundled.js'
import type { OntologyMap } from './ontology-map'
import { labelSize } from './ontology-map-links'

export interface Point {
  x: number
  y: number
}

export interface Size {
  width: number
  height: number
}

/** A class's node is this size unless the Map gives it another, as a comparison does a class it expands. */
export const NODE_SIZE = { width: 160, height: 40 } as const

/** How far apart, centre to centre, the layout aims to put two linked classes. */
const EDGE_LENGTH = 220
/** The clearance a link label keeps from the classes at either end. */
const LABEL_CLEARANCE = 32
/** The least space kept between two classes' nodes. */
const NODE_GAP = 24

const elk = new ELK()

/**
 * Where each class goes: the top-left corner of its node, by class label. A stress
 * layout from a seeded force layout, so the same Map always lays out the same way. Each
 * pair of linked classes pulls together once, however many links run between them, and
 * a subclass link pulls like a Pattern link, so subclasses sit near their superclass.
 * Each pair stays far enough apart for the widest label between them to sit clear of
 * both classes, even side by side.
 *
 * Classes are laid out as uniform nodes, then spread apart by one factor until no node
 * of its size (`sizes`, by class label, else `NODE_SIZE`) overlaps another. Sizes only
 * spread the Map, so every class keeps its place relative to the others.
 */
export async function layoutOntologyMap(
  map: OntologyMap,
  sizes: Record<string, Size> = {},
): Promise<Record<string, Point>> {
  // The widest label between each linked pair: 0 for a subclass link, which has none.
  const pairs = new Map<string, number>()
  const pull = (a: string, b: string, labelWidth: number) => {
    if (a === b) return
    const key = JSON.stringify([a, b].sort())
    pairs.set(key, Math.max(pairs.get(key) ?? 0, labelWidth))
  }
  for (const l of map.links) pull(l.source, l.target, labelSize(l.relation).width)
  for (const l of map.subclassLinks) pull(l.child, l.parent, 0)
  const graph = await elk.layout({
    id: 'root',
    layoutOptions: {
      'elk.algorithm': 'stress',
      'elk.stress.desiredEdgeLength': String(EDGE_LENGTH),
      // Stress starts from a force layout, which takes nearly all the time: each
      // iteration costs ~2.5 ms at 100 classes (the default 300 took ~0.7 s alone). Stress
      // untangles a rough start just as well, with no more crossings, so a few will do.
      'elk.force.iterations': '10',
      'elk.randomSeed': '1',
    },
    children: map.nodes.map((n) => ({ id: n.label, ...NODE_SIZE })),
    edges: [...pairs].map(([key, labelWidth]) => {
      const [source, target] = JSON.parse(key) as [string, string]
      const length = Math.max(EDGE_LENGTH, NODE_SIZE.width + labelWidth + 2 * LABEL_CLEARANCE)
      return {
        id: key,
        sources: [source],
        targets: [target],
        layoutOptions: { 'elk.stress.desiredEdgeLength': String(length) },
      }
    }),
  })
  const nodes = (graph.children ?? []).map((n) => ({
    label: n.id,
    centre: { x: (n.x ?? 0) + NODE_SIZE.width / 2, y: (n.y ?? 0) + NODE_SIZE.height / 2 },
    size: sizes[n.id] ?? NODE_SIZE,
  }))
  const spread = spreadApart(nodes)
  return Object.fromEntries(
    nodes.map(({ label, centre, size }) => [
      label,
      { x: centre.x * spread - size.width / 2, y: centre.y * spread - size.height / 2 },
    ]),
  )
}

/**
 * The least factor, at least 1, by which to spread `nodes`' centres so that no two of
 * them overlap: a pair is apart once it is apart along either axis.
 */
function spreadApart(nodes: { centre: Point; size: Size }[]): number {
  let spread = 1
  for (const [i, a] of nodes.entries()) {
    for (const b of nodes.slice(i + 1)) {
      // Classes the layout puts on one spot no spread can part.
      if (a.centre.x === b.centre.x && a.centre.y === b.centre.y) continue
      const along = (axis: 'x' | 'y', extent: 'width' | 'height') =>
        ((a.size[extent] + b.size[extent]) / 2 + NODE_GAP) / Math.abs(a.centre[axis] - b.centre[axis])
      spread = Math.max(spread, Math.min(along('x', 'width'), along('y', 'height')))
    }
  }
  return spread
}
