/**
 * PROTOTYPE (throwaway, branch prototype/ontology-map-d3): one layout for every
 * Ontology Version of a Knowledge Graph, drawn with d3-force only (ADR 0014).
 *
 * Two modes, so the prototype can compare them:
 *
 * - `anchored`: versions are laid out oldest first. A class keeps the place it got in the
 *   first version that declared it, for good: later versions only place their *new*
 *   classes, next to their already-placed neighbours, around the fixed ones. Registering a
 *   new version never moves anything that was already drawn.
 * - `union`: one layout of every class any version declared. Every version agrees, but
 *   registering a new version can reshuffle the whole Map once.
 *
 * Deterministic: d3-force seeds its own LCG, nodes go in sorted by label, and new
 * classes start from a hash of their label, so the same history always lays out the same.
 */
import { forceLink, forceManyBody, forceSimulation, forceX, forceY, type SimulationNodeDatum } from 'd3'
import type { Ontology } from '@/api/ontology-versions'

export interface Size {
  width: number
  height: number
}
export interface Point {
  x: number
  y: number
}
export type LayoutMode = 'anchored' | 'union'

interface LNode extends SimulationNodeDatum {
  id: string
  w: number
  h: number
}

/** A stable pseudo-random number in [0, 1) from a string (FNV-1a). */
export function hash(s: string): number {
  let h = 2166136261
  for (let i = 0; i < s.length; i++) {
    h ^= s.charCodeAt(i)
    h = Math.imul(h, 16777619)
  }
  return (h >>> 0) / 2 ** 32
}

const pairKey = (a: string, b: string) => JSON.stringify([a, b].sort())

/** Each linked pair of classes once (Patterns and superclasses), and the superclass links. */
function edgesOf(o: Ontology) {
  const labels = new Set(o.node_types.map((n) => n.label))
  const pairs = new Map<string, [string, string]>()
  for (const [s, , t] of o.patterns) {
    if (s === t || !labels.has(s) || !labels.has(t)) continue
    pairs.set(pairKey(s, t), [s, t].sort() as [string, string])
  }
  const subclass = o.node_types
    .filter((n) => n.parent !== undefined && labels.has(n.parent) && n.parent !== n.label)
    .map((n) => [n.label, n.parent!] as [string, string])
  for (const [c, p] of subclass) pairs.delete(pairKey(c, p))
  return { pairs: [...pairs.values()], subclass }
}

/** Every class and Pattern any of `versions` declares; a class's latest superclass wins. */
export function unionOntology(versions: Ontology[]): Ontology {
  const classes = new Map<string, Ontology['node_types'][number]>()
  const patterns = new Map<string, [string, string, string]>()
  for (const v of versions) {
    for (const n of v.node_types) classes.set(n.label, n)
    for (const p of v.patterns) patterns.set(JSON.stringify(p), p)
  }
  return { node_types: [...classes.values()], relationship_types: [], patterns: [...patterns.values()] }
}

/** Boxes never overlap: pushes apart along the axis they overlap least, by position, not velocity. */
function rectCollide(gap: number) {
  let nodes: LNode[] = []
  const force = () => {
    for (let i = 0; i < nodes.length; i++) {
      for (let j = i + 1; j < nodes.length; j++) {
        const a = nodes[i]
        const b = nodes[j]
        const dx = b.x! - a.x!
        const dy = b.y! - a.y!
        const ox = (a.w + b.w) / 2 + gap - Math.abs(dx)
        const oy = (a.h + b.h) / 2 + gap - Math.abs(dy)
        if (ox <= 0 || oy <= 0) continue
        const aFree = a.fx == null
        const bFree = b.fx == null
        if (!aFree && !bFree) continue
        const [shareA, shareB] = aFree && bFree ? [0.5, 0.5] : aFree ? [1, 0] : [0, 1]
        // Wide boxes: prefer separating vertically unless they mostly sit side by side.
        if (ox / (a.w + b.w) < oy / (a.h + b.h)) {
          const s = dx === 0 ? (hash(a.id + b.id) < 0.5 ? -1 : 1) : Math.sign(dx)
          a.x! -= s * ox * shareA
          b.x! += s * ox * shareB
        } else {
          const s = dy === 0 ? (hash(b.id + a.id) < 0.5 ? -1 : 1) : Math.sign(dy)
          a.y! -= s * oy * shareA
          b.y! += s * oy * shareB
        }
      }
    }
  }
  force.initialize = (n: LNode[]) => {
    nodes = n
  }
  return force
}

/** A subclass sits below its superclass, so inheritance always reads top-down. */
function hierarchyDown(subclass: [string, string][], minGap: number) {
  let byId = new Map<string, LNode>()
  const force = (alpha: number) => {
    for (const [c, p] of subclass) {
      const child = byId.get(c)
      const parent = byId.get(p)
      if (!child || !parent) continue
      const need = (child.h + parent.h) / 2 + minGap - (child.y! - parent.y!)
      if (need <= 0) continue
      const k = need * alpha * 0.6
      if (child.fy == null) child.vy! += parent.fy == null ? k / 2 : k
      if (parent.fy == null) parent.vy! -= child.fy == null ? k / 2 : k
    }
  }
  force.initialize = (n: LNode[]) => {
    byId = new Map(n.map((d) => [d.id, d]))
  }
  return force
}

/**
 * No line runs through a class it doesn't belong to: a class within `pad` of another
 * pair's line is pushed off it sideways (or, if that class is fixed, the line's free ends are).
 */
function edgesClearNodes(edges: [string, string][], pad: number) {
  let nodes: LNode[] = []
  let byId = new Map<string, LNode>()
  const force = (alpha: number) => {
    for (const [ia, ib] of edges) {
      const a = byId.get(ia)
      const b = byId.get(ib)
      if (!a || !b) continue
      const [sx, sy] = [b.x! - a.x!, b.y! - a.y!]
      const len2 = sx * sx + sy * sy || 1
      for (const n of nodes) {
        if (n === a || n === b) continue
        const t = ((n.x! - a.x!) * sx + (n.y! - a.y!) * sy) / len2
        if (t <= 0.05 || t >= 0.95) continue
        const [px, py] = [a.x! + t * sx, a.y! + t * sy]
        let [dx, dy] = [n.x! - px, n.y! - py]
        // How deep inside the class's padded box the line's nearest point is, 0..1.
        const inside = 1 - Math.max(Math.abs(dx) / (n.w / 2 + pad), Math.abs(dy) / (n.h / 2 + pad))
        if (inside <= 0) continue
        const d = Math.hypot(dx, dy)
        if (d < 1e-6) [dx, dy] = [-sy / Math.sqrt(len2), sx / Math.sqrt(len2)]
        else [dx, dy] = [dx / d, dy / d]
        const k = inside * alpha * 40
        if (n.fx == null) {
          n.vx! += dx * k
          n.vy! += dy * k
        } else {
          for (const end of [a, b])
            if (end.fx == null) {
              end.vx! -= dx * k * 0.5
              end.vy! -= dy * k * 0.5
            }
        }
      }
    }
  }
  force.initialize = (n: LNode[]) => {
    nodes = n
    byId = new Map(n.map((d) => [d.id, d]))
  }
  return force
}

/**
 * Lays `ontology` out around the classes in `fixed`, which do not move (they are also
 * obstacles, even those this version dropped, so a new class never takes a removed
 * class's place). Returns `fixed` plus a place for each new class.
 */
function simulate(ontology: Ontology, sizeOf: (label: string) => Size, fixed: Map<string, Point>) {
  const labels = [...new Set([...ontology.node_types.map((n) => n.label), ...fixed.keys()])].sort()
  const { pairs, subclass } = edgesOf(ontology)
  const neighbours = new Map<string, string[]>()
  for (const [a, b] of [...pairs, ...subclass]) {
    neighbours.set(a, [...(neighbours.get(a) ?? []), b])
    neighbours.set(b, [...(neighbours.get(b) ?? []), a])
  }
  const xs = [...fixed.values()].map((p) => p.x)
  const ys = [...fixed.values()].map((p) => p.y)
  let outside = 0
  const nodes: LNode[] = labels.map((id) => {
    const { width: w, height: h } = sizeOf(id)
    const f = fixed.get(id)
    if (f) return { id, w, h, x: f.x, y: f.y, fx: f.x, fy: f.y }
    const placed = (neighbours.get(id) ?? []).map((n) => fixed.get(n)).filter((p): p is Point => !!p)
    const angle = hash(id) * 2 * Math.PI
    if (placed.length > 0) {
      const mx = placed.reduce((s, p) => s + p.x, 0) / placed.length
      const my = placed.reduce((s, p) => s + p.y, 0) / placed.length
      return { id, w, h, x: mx + Math.cos(angle) * 160, y: my + Math.sin(angle) * 90 }
    }
    if (fixed.size > 0) {
      // Unconnected to anything placed: start in a column right of the drawing.
      outside++
      return { id, w, h, x: Math.max(...xs) + 260, y: Math.min(...ys) + outside * 70 }
    }
    return { id, w, h } // d3's phyllotaxis start
  })
  const byId = new Map(nodes.map((n) => [n.id, n]))
  const links = [
    ...pairs.map(([a, b]) => ({ source: a, target: b, sub: false })),
    ...subclass.map(([c, p]) => ({ source: c, target: p, sub: true })),
  ]
  const sim = forceSimulation(nodes)
    .force(
      'link',
      forceLink<LNode, (typeof links)[number]>(links)
        .id((d) => d.id)
        .distance((l) => {
          const a = byId.get(typeof l.source === 'string' ? l.source : (l.source as LNode).id)!
          const b = byId.get(typeof l.target === 'string' ? l.target : (l.target as LNode).id)!
          // Room for the relation labels between the boxes; a superclass sits just above.
          return l.sub ? (a.h + b.h) / 2 + 70 : (a.w + b.w) / 2 + 160
        })
        .strength(0.7),
    )
    .force('charge', forceManyBody<LNode>().strength(-700).distanceMax(700))
    // A landscape Map: pulled harder vertically than horizontally.
    .force('x', forceX<LNode>(0).strength(0.015))
    .force('y', forceY<LNode>(0).strength(0.05))
    .force('down', hierarchyDown(subclass, 60))
    .force('clear', edgesClearNodes([...pairs, ...subclass], 22))
    .force('collide', rectCollide(28))
    .stop()
  for (let i = 0; i < 400; i++) sim.tick()
  // Settle what is left of any overlap.
  // Settle what is left of any overlap: each new class still on top of another moves to
  // the nearest clear spot on a spiral around where the simulation left it.
  const GAP = 20
  const clash = (a: LNode, x: number, y: number, b: LNode) =>
    Math.abs(x - b.x!) < (a.w + b.w) / 2 + GAP && Math.abs(y - b.y!) < (a.h + b.h) / 2 + GAP
  const settled = nodes.filter((n) => n.fx != null)
  for (const n of nodes.filter((d) => d.fx == null)) {
    const clear = (x: number, y: number) => settled.every((s) => !clash(n, x, y, s))
    if (!clear(n.x!, n.y!)) {
      search: for (let r = 20; r < 4000; r += 20) {
        for (let k = 0; k < 24; k++) {
          const a = (k / 24) * 2 * Math.PI
          const [x, y] = [n.x! + Math.cos(a) * r * 1.6, n.y! + Math.sin(a) * r]
          if (clear(x, y)) {
            n.x = x
            n.y = y
            break search
          }
        }
      }
    }
    settled.push(n)
  }
  return new Map(nodes.map((n) => [n.id, { x: Math.round(n.x!), y: Math.round(n.y!) }]))
}

/** Where each class of any of `versions` (oldest first) goes, centre by label. */
export function stableLayout(
  versions: Ontology[],
  mode: LayoutMode,
  sizeOf: (label: string) => Size,
): Map<string, Point> {
  if (versions.length === 0) return new Map()
  if (mode === 'union') return simulate(unionOntology(versions), sizeOf, new Map())
  let placed = new Map<string, Point>()
  for (const v of versions) placed = simulate(v, sizeOf, placed)
  return placed
}

/** The box around every placed class, so the first view frames the same area for every version. */
export function boundsOf(positions: Map<string, Point>, sizeOf: (label: string) => Size) {
  let [x0, y0, x1, y1] = [Infinity, Infinity, -Infinity, -Infinity]
  for (const [label, p] of positions) {
    const { width, height } = sizeOf(label)
    x0 = Math.min(x0, p.x - width / 2)
    y0 = Math.min(y0, p.y - height / 2)
    x1 = Math.max(x1, p.x + width / 2)
    y1 = Math.max(y1, p.y + height / 2)
  }
  return positions.size === 0 ? { x0: 0, y0: 0, x1: 1, y1: 1 } : { x0, y0, x1, y1 }
}
