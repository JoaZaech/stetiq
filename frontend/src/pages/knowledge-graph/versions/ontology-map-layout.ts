/** Where each class of the Map goes: a seeded ELK stress layout. */
import ELK from 'elkjs/lib/elk.bundled.js'
import type { OntologyMap } from './ontology-map'

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

/** The least space kept between two classes' nodes. */
const NODE_GAP = 24

const elk = new ELK()

/**
 * Where each class goes: the top-left corner of its node, by class label. A stress
 * layout from a seeded force layout, so the same Map always lays out the same way. Each
 * pair of linked classes pulls together once, however many links run between them, and
 * a subclass link pulls like a Pattern link, so subclasses sit near their superclass.
 *
 * Classes are laid out as uniform nodes, then spread apart by one factor until no node
 * of its size (`sizes`, by class label, else `NODE_SIZE`) overlaps another. Sizes only
 * spread the Map, so every class keeps its place relative to the others.
 */
export async function layoutOntologyMap(
  map: OntologyMap,
  sizes: Record<string, Size> = {},
): Promise<Record<string, Point>> {
  const pairs = new Set(
    [
      ...map.links.map((l) => [l.source, l.target]),
      ...map.subclassLinks.map((l) => [l.child, l.parent]),
    ]
      .filter(([a, b]) => a !== b)
      .map((pair) => JSON.stringify(pair.sort())),
  )
  const graph = await elk.layout({
    id: 'root',
    layoutOptions: {
      'elk.algorithm': 'stress',
      'elk.stress.desiredEdgeLength': '220',
      // Stress starts from a force layout, whose default 300 iterations take most of
      // the time (~0.7 s at 100 classes); stress refines a rougher start just as well.
      'elk.force.iterations': '100',
      'elk.randomSeed': '1',
    },
    children: map.nodes.map((n) => ({ id: n.label, ...NODE_SIZE })),
    edges: [...pairs].map((key) => {
      const [source, target] = JSON.parse(key) as [string, string]
      return { id: key, sources: [source], targets: [target] }
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
