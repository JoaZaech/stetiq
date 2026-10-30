/** Where each class of the Map goes: a seeded ELK stress layout. */
import ELK from 'elkjs/lib/elk.bundled.js'
import type { OntologyMap } from './ontology-map'
import { labelSize } from './ontology-map-links'

export interface Point {
  x: number
  y: number
}

/** Every node is drawn this size: nodes are uniform until Observed statistics size them. */
export const NODE_SIZE = { width: 160, height: 40 } as const

/** How far apart, centre to centre, the layout aims to put two linked classes. */
const EDGE_LENGTH = 220
/** The clearance a link label keeps from the classes at either end. */
const LABEL_CLEARANCE = 32

const elk = new ELK()

/**
 * Where each class goes: the top-left corner of its node, by class label. A stress
 * layout from a seeded force layout, so the same Map always lays out the same way. Each
 * pair of linked classes pulls together once, however many links run between them, and
 * a subclass link pulls like a Pattern link, so subclasses sit near their superclass.
 * Each pair stays far enough apart for the widest label between them to sit clear of
 * both classes, even side by side.
 */
export async function layoutOntologyMap(map: OntologyMap): Promise<Record<string, Point>> {
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
      // Stress starts from a force layout, whose default 300 iterations take most of
      // the time (~0.7 s at 100 classes); stress refines a rougher start just as well.
      'elk.force.iterations': '100',
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
  return Object.fromEntries((graph.children ?? []).map((n) => [n.id, { x: n.x ?? 0, y: n.y ?? 0 }]))
}
