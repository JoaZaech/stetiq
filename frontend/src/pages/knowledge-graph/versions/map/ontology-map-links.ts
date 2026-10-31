/** How the Map draws a Pattern link and its relation label, and when the label shows. */
import type { PatternLink } from './ontology-map'
import type { MapChange } from '../comparison/ontology-map-comparison'
import type { Point } from './ontology-map-layout'
import { labelSize, type Size } from './ontology-map-sizes'

/** A rectangle by its top-left corner: a class's node on the Map, or a label's pill. */
export type Box = Point & Size

/**
 * The least zoom at which a link's label can be read: below it only the labels that matter
 * right now show (see `labelShown`). Fit-to-view stops above it, at `FIT_MIN_ZOOM`.
 */
export const READABLE_ZOOM = 0.7

/**
 * Whether a link's label shows at `zoom`: always when readable, and below that only on a
 * link `focused` by the selection or changed in a comparison (cosmetically, changed
 * only cosmetically, does not count), so a zoomed-out Map keeps the labels being looked at.
 */
export function labelShown(zoom: number, link: { focused: boolean; change?: MapChange }): boolean {
  const changed = link.change !== undefined && !['unchanged', 'cosmetic'].includes(link.change.kind)
  return zoom >= READABLE_ZOOM || link.focused || changed
}

/** Pixels between parallel links, per unit of a `line` route's bend. */
const BEND_SPACING = 48
/** How far along a link its label moves, per unit of bend, so parallel links' labels stagger. */
const LABEL_STAGGER = 0.2
/** How far the smallest self-loop reaches out of its class, and how much each further loop adds. */
const LOOP_REACH = 48
const LOOP_STEP = 24

/** How a link is drawn: its SVG path and the box its label sits in. */
export interface LinkShape {
  path: string
  label: Box
}

/** A Pattern link drawn between its classes' nodes, each by its box on the Map. */
export function linkShape(link: Pick<PatternLink, 'relation' | 'route'>, from: Box, to: Box): LinkShape {
  const size = labelSize(link.relation)
  return link.route.kind === 'loop'
    ? loopShape(from, link.route.size, size)
    : lineShape(from, to, link.route.bend, size)
}

/** A straight line between two nodes' boxes, from boundary to boundary. */
export const straightPath = (from: Box, to: Box): string => lineShape(from, to, 0, { width: 0, height: 0 }).path

const center = ({ x, y, width, height }: Box): Point => ({ x: x + width / 2, y: y + height / 2 })

/** Where the ray from a node's centre towards `toward` leaves the node's box. */
function boundary(node: Box, toward: Point): Point {
  const c = center(node)
  const dx = toward.x - c.x
  const dy = toward.y - c.y
  if (dx === 0 && dy === 0) return c
  const scale = 1 / Math.max(Math.abs(dx) / (node.width / 2), Math.abs(dy) / (node.height / 2))
  return { x: c.x + dx * scale, y: c.y + dy * scale }
}

const centredOn = (p: Point, size: Size): Box => ({ x: p.x - size.width / 2, y: p.y - size.height / 2, ...size })

/**
 * A quadratic curve between two classes' boxes, bent `bend` spacings to the left of
 * from → to. Its label sits on the curve, moved along it by the bend: parallel links bend
 * apart and their labels also step along the pair, so labels never sit side by side,
 * whichever way the pair runs.
 */
function lineShape(from: Box, to: Box, bend: number, size: Size): LinkShape {
  const [a, b] = [center(from), center(to)]
  const length = Math.hypot(b.x - a.x, b.y - a.y) || 1
  // Left of a → b in screen coordinates, where y grows downwards.
  const normal = { x: (b.y - a.y) / length, y: -(b.x - a.x) / length }
  // A quadratic's midpoint lies halfway to its control point: twice the offset bends it by one.
  const control = {
    x: (a.x + b.x) / 2 + normal.x * bend * BEND_SPACING * 2,
    y: (a.y + b.y) / 2 + normal.y * bend * BEND_SPACING * 2,
  }
  const start = boundary(from, control)
  const end = boundary(to, control)
  // A link running the other way has the opposite bend and runs from the other end, so
  // its label steps the same way along the pair as its slot.
  const t = Math.min(0.9, Math.max(0.1, 0.5 + bend * LABEL_STAGGER))
  const at = (p: number, q: number, r: number) => (1 - t) ** 2 * p + 2 * t * (1 - t) * q + t ** 2 * r
  return {
    path: `M ${start.x} ${start.y} Q ${control.x} ${control.y} ${end.x} ${end.y}`,
    label: centredOn({ x: at(start.x, control.x, end.x), y: at(start.y, control.y, end.y) }, size),
  }
}

/**
 * An arc out of a class's right end and back, where links between classes (centre to
 * centre, through the wide node's top or bottom) rarely leave; larger loops nest outside
 * smaller ones. Its label starts just outside the arc.
 */
function loopShape(node: Box, loop: number, size: Size): LinkShape {
  const c = center(node)
  const right = node.x + node.width
  const reach = LOOP_REACH + LOOP_STEP * (loop - 1)
  const spread = 8 + 6 * (loop - 1)
  const [y0, y1] = [c.y - spread, c.y + spread]
  return {
    path: `M ${right} ${y0} C ${right + reach} ${y0 - spread * 2}, ${right + reach} ${y1 + spread * 2}, ${right} ${y1}`,
    // A cubic's midpoint: 3/4 of the way to its control points, here just outside the arc.
    label: { x: right + reach * 0.75 + 4, y: c.y - size.height / 2, ...size },
  }
}
