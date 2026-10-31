/** Where each class of the Map goes: a seeded ELK stress layout. */
import ELK from 'elkjs/lib/elk.bundled.js'
import type { OntologyMap } from './ontology-map'
import { labelSize, NODE_SIZE, type Size } from './ontology-map-sizes'

export interface Point {
  x: number
  y: number
}

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
 * Classes are laid out as uniform nodes, turned to lie wide (a stress layout has no
 * orientation of its own, and the Map is wider than tall), then each drawn at its size
 * (`sizes`, by class label, else `NODE_SIZE`) and moved apart where two overlap, by ELK's
 * SPOrE overlap removal. Only colliding classes move, outward from each other, so every
 * class keeps its place relative to the others, and a larger class leaves the far side
 * of the Map as it was.
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
  const laidOut = (graph.children ?? []).map((n) => ({
    label: n.id,
    centre: { x: (n.x ?? 0) + NODE_SIZE.width / 2, y: (n.y ?? 0) + NODE_SIZE.height / 2 },
  }))
  const looped = new Set(map.links.filter((l) => l.source === l.target).map((l) => l.source))
  const linked = [...pairs.keys()].map((key) => JSON.parse(key) as [string, string])
  const turned = landscape(laidOut, looped, linked)
  const apart = await elk.layout({
    id: 'root',
    layoutOptions: { 'elk.algorithm': 'sporeOverlap', 'elk.spacing.nodeNode': String(NODE_GAP) },
    children: turned.map(({ label, centre }) => {
      const size = sizes[label] ?? NODE_SIZE
      return { id: label, x: centre.x - size.width / 2, y: centre.y - size.height / 2, ...size }
    }),
  })
  return Object.fromEntries((apart.children ?? []).map((n) => [n.id, { x: n.x ?? 0, y: n.y ?? 0 }]))
}

/** The four quarter turns about the origin: none, a quarter, a half and three quarters. */
const QUARTER_TURNS: ((p: Point) => Point)[] = [
  (p) => p,
  ({ x, y }) => ({ x: -y, y: x }),
  ({ x, y }) => ({ x: -x, y: -y }),
  ({ x, y }) => ({ x: y, y: -x }),
]

/**
 * `nodes` given the quarter turn that leaves the fewest links out of a `looped` class's
 * right end, where its self-loops are drawn, and of those, one that lays them out wide,
 * as the Map is. A stress layout has no orientation of its own; only quarter turns,
 * so classes the layout lines up across or down stay lined up.
 */
function landscape<T extends { label: string; centre: Point }>(
  nodes: T[],
  looped: ReadonlySet<string>,
  linked: [string, string][],
): T[] {
  const extent = (turned: T[], axis: 'x' | 'y') =>
    Math.max(...turned.map((n) => n.centre[axis])) - Math.min(...turned.map((n) => n.centre[axis]))
  const inLoopsWay = (turned: T[]) => {
    const at = new Map(turned.map((n) => [n.label, n.centre]))
    const rightOf = (a: string, b: string) => {
      const [p, q] = [at.get(a)!, at.get(b)!]
      // A link to `b` leaves `a` through its right end, where the loops are.
      return looped.has(a) && (q.x - p.x) * NODE_SIZE.height > Math.abs(q.y - p.y) * NODE_SIZE.width
    }
    return linked.filter(([a, b]) => rightOf(a, b) || rightOf(b, a)).length
  }
  const scored = QUARTER_TURNS.map((turn) => {
    const turned = nodes.map((n) => ({ ...n, centre: turn(n.centre) }))
    return { turned, inLoopsWay: inLoopsWay(turned), tall: extent(turned, 'y') > extent(turned, 'x') }
  })
  // The first of the best, so the same layout always turns the same way.
  const better = (a: (typeof scored)[number], b: (typeof scored)[number]) =>
    a.inLoopsWay !== b.inLoopsWay ? a.inLoopsWay < b.inLoopsWay : !a.tall && b.tall
  return scored.reduce((best, s) => (better(s, best) ? s : best)).turned
}
