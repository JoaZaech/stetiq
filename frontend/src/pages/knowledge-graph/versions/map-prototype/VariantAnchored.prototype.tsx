/**
 * PROTOTYPE variant A, "Anchored map": the node-link Map, redrawn in d3.
 *
 * Concise: one line per pair of classes, however many relations run between them, with
 * each relation on it as `NAME →` / `← NAME` read left to right, so parallel relations
 * never fan out or overlap. A class shows its name and attribute count only.
 * Accurate: arrowheads at each end a relation points to; subclass links are dashed with
 * a hollow UML triangle and always run upwards to the superclass; self-relations sit as
 * a loop on top of their class. Readable: class positions never change between versions
 * (stable layout), the view frames every class of the history so it doesn't jump, and
 * zoomed out only the labels of the focused or changed links stay.
 */
import { useEffect, useId, useRef, useState } from 'react'
import { select, transition, zoom, zoomIdentity } from 'd3'
import type { VariantProps } from './variants.prototype'
import { NAME_SIZE } from './sizes.prototype'
import { mono, type Bundle, type ClassItem, type Rel, type Status } from './schema-view.prototype'
import { boundsOf, type Point, type Size } from './stable-layout.prototype'

const LABEL_SIZE = 11
const MAX_LINES = 3
/** Zoomed out further than this, only focused or changed links keep their labels. */
const READABLE = 0.6


const COLOR: Record<Status, string> = {
  kept: 'var(--muted-foreground)',
  added: 'var(--diff-additive)',
  removed: 'var(--diff-breaking)',
}

type Box = Point & Size

const boxOf = (p: Point, s: Size): Box => ({ x: p.x - s.width / 2, y: p.y - s.height / 2, ...s })

/** Where the ray from the box's centre toward `to` leaves it, `pad` px outside. */
function boundary(b: Box, to: Point, pad = 4): Point {
  const c = { x: b.x + b.width / 2, y: b.y + b.height / 2 }
  const [dx, dy] = [to.x - c.x, to.y - c.y]
  if (dx === 0 && dy === 0) return c
  const scale = 1 / Math.max(Math.abs(dx) / (b.width / 2 + pad), Math.abs(dy) / (b.height / 2 + pad))
  return { x: c.x + dx * scale, y: c.y + dy * scale }
}

const groupStatus = (rels: { status: Status }[]): Status =>
  rels.every((r) => r.status === 'added') ? 'added' : rels.every((r) => r.status === 'removed') ? 'removed' : 'kept'

export function VariantAnchored({ view, positions, sizeOf, query, selected, onSelect }: VariantProps) {
  const svgRef = useRef<SVGSVGElement>(null)
  const gRef = useRef<SVGGElement>(null)
  const zoomK = useRef(1)
  const [hover, setHover] = useState<string | null>(null)
  const uid = useId().replace(/[^a-zA-Z0-9]/g, '')

  // Zoom, framing every class any version has, so switching versions never moves the view.
  useEffect(() => {
    const svg = select(svgRef.current!)
    const g = select(gRef.current!)
    const z = zoom<SVGSVGElement, unknown>()
      .scaleExtent([0.1, 3])
      .on('zoom', (e) => {
        g.attr('transform', e.transform.toString())
        zoomK.current = e.transform.k
        g.selectAll<SVGGElement, { show: boolean }>('g.rel-label').attr('display', (d) =>
          d.show || zoomK.current >= READABLE ? null : 'none',
        )
      })
    svg.call(z).on('dblclick.zoom', null)
    const { width, height } = svgRef.current!.getBoundingClientRect()
    const b = boundsOf(positions, sizeOf)
    const k = Math.min(1.1, 0.9 * Math.min(width / (b.x1 - b.x0 + 120), height / (b.y1 - b.y0 + 200)))
    svg.call(z.transform, zoomIdentity.translate(width / 2, height / 2 + 10).scale(k).translate(-(b.x0 + b.x1) / 2, -(b.y0 + b.y1) / 2))
    return () => {
      svg.on('.zoom', null)
    }
  }, [positions, sizeOf])

  useEffect(() => {
    const g = select(gRef.current!)
    const T = transition().duration(350)
    const at = (l: string) => positions.get(l) ?? { x: 0, y: 0 }
    const box = (l: string) => boxOf(at(l), sizeOf(l))

    // What is in focus: the hovered (else selected) class and its neighbours, else the search's matches.
    const focus = hover ?? selected
    const near = new Set<string>()
    if (focus) {
      near.add(focus)
      for (const b of view.bundles) if (b.a === focus || b.b === focus) near.add(b.a).add(b.b)
      for (const s of view.subclass) if (s.child === focus || s.parent === focus) near.add(s.child).add(s.parent)
    }
    const q = query.trim().toLowerCase()
    const matches = new Set(
      q
        ? view.classes
            .filter((c) => c.label.toLowerCase().includes(q) || c.attributes.some((a) => a.name.toLowerCase().includes(q)))
            .map((c) => c.label)
        : [],
    )
    const dimmedClass = (l: string) => (focus ? !near.has(l) : q ? !matches.has(l) : false)
    const touches = (a: string, b: string) => (focus ? a === focus || b === focus : q ? matches.has(a) || matches.has(b) : false)
    const dimmedLink = (a: string, b: string) => (focus || q ? !touches(a, b) : false)

    // Subclass links: dashed, hollow triangle at the superclass.
    g.select('g.subclass')
      .selectAll<SVGPathElement, (typeof view.subclass)[number]>('path')
      .data(view.subclass, (d) => `${d.child}>${d.parent}`)
      .join(
        (enter) => enter.append('path').attr('opacity', 0),
        (update) => update,
        (exit) => exit.transition(T).attr('opacity', 0).remove(),
      )
      .attr('fill', 'none')
      .attr('stroke-dasharray', '5 4')
      .attr('stroke-width', 1.25)
      .style('stroke', (d) => COLOR[d.status])
      .attr('marker-end', `url(#${uid}-tri)`)
      .transition(T)
      .attr('opacity', (d) => (dimmedLink(d.child, d.parent) ? 0.12 : 1))
      .attr('d', (d) => {
        const [c, p] = [box(d.child), box(d.parent)]
        const s = boundary(c, at(d.parent))
        const e = boundary(p, at(d.child), 9)
        return `M${s.x},${s.y}L${e.x},${e.y}`
      })

    // Pattern bundles: one line per pair of classes.
    type Drawn = Bundle & { left: string; right: string; show: boolean; status: Status }
    const drawn: Drawn[] = view.bundles.map((b) => {
      const [left, right] = at(b.a).x <= at(b.b).x ? [b.a, b.b] : [b.b, b.a]
      const status = groupStatus(b.relations)
      const changed = b.relations.some((r) => r.status !== 'kept')
      return { ...b, left, right, status, show: touches(b.a, b.b) || changed }
    })
    const bundles = g
      .select('g.bundles')
      .selectAll<SVGGElement, Drawn>('g.bundle')
      .data(drawn, (d) => d.key)
      .join(
        (enter) => {
          const e = enter.append('g').attr('class', 'bundle').attr('opacity', 0)
          e.append('path').attr('class', 'line').attr('fill', 'none')
          return e
        },
        (update) => update,
        (exit) => exit.transition(T).attr('opacity', 0).remove(),
      )
    bundles.transition(T).attr('opacity', (d) => (dimmedLink(d.a, d.b) ? 0.12 : 1))
    bundles
      .select<SVGPathElement>('path.line')
      .attr('stroke-width', (d) => (touches(d.a, d.b) ? 2 : 1.25))
      .style('stroke', (d) => COLOR[d.status])
      .attr('stroke-dasharray', (d) => (d.status === 'removed' ? '3 3' : null))
      .attr('marker-end', (d) => (d.relations.some((r) => r.source === d.left) ? `url(#${uid}-arrow-${d.status})` : null))
      .attr('marker-start', (d) => (d.relations.some((r) => r.source === d.right) ? `url(#${uid}-arrow-${d.status})` : null))
      .transition(T)
      .attr('d', (d) => {
        const s = boundary(box(d.left), at(d.right))
        const e = boundary(box(d.right), at(d.left))
        return `M${s.x},${s.y}L${e.x},${e.y}`
      })

    // Relation labels, on the line's midpoint, one line per relation.
    const labels = g
      .select('g.labels')
      .selectAll<SVGGElement, Drawn>('g.rel-label')
      .data(drawn, (d) => d.key)
      .join(
        (enter) => {
          const e = enter.append('g').attr('class', 'rel-label').attr('opacity', 0)
          e.append('rect').attr('rx', 4)
          e.append('text').attr('font-family', 'ui-monospace, monospace').attr('font-size', LABEL_SIZE)
          return e
        },
        (update) => update,
        (exit) => exit.transition(T).attr('opacity', 0).remove(),
      )
      .attr('display', (d) => (d.show || zoomK.current >= READABLE ? null : 'none'))
    type Line = { text: string; status: Status; deprecated: boolean }
    const linesOf = (d: Drawn): Line[] => {
      const lines: Line[] = d.relations.slice(0, MAX_LINES).map((r: Rel) => ({
        text: r.source === d.left ? `${r.relation} →` : `← ${r.relation}`,
        status: r.status,
        deprecated: r.deprecated,
      }))
      if (d.relations.length > MAX_LINES) lines.push({ text: `+${d.relations.length - MAX_LINES} more`, status: 'kept', deprecated: false })
      return lines
    }
    labels.each(function (d) {
      const lines = linesOf(d)
      const w = Math.max(...lines.map((l) => mono(l.text, LABEL_SIZE))) + 10
      const h = lines.length * 13 + 5
      const sel = select(this)
      sel
        .select('rect')
        .attr('x', -w / 2)
        .attr('y', -h / 2)
        .attr('width', w)
        .attr('height', h)
        .style('fill', 'var(--background)')
        .style('stroke', d.status === 'kept' ? 'none' : COLOR[d.status])
      sel
        .select('text')
        .selectAll<SVGTSpanElement, Line>('tspan')
        .data(lines)
        .join('tspan')
        .attr('x', 0)
        .attr('y', (_, i) => -h / 2 + 12 + i * 13)
        .attr('text-anchor', 'middle')
        .style('fill', (l) => (l.status === 'kept' ? 'var(--foreground)' : COLOR[l.status]))
        .style('text-decoration', (l) => (l.status === 'removed' || l.deprecated ? 'line-through' : null))
        .text((l) => l.text)
    })
    // Each label at the first point along its line, from the middle outwards, where it
    // covers no class and no label placed before it; else the middle.
    const classBoxes = view.classes.map((c) => box(c.label))
    const placed: Box[] = []
    const hit = (r: Box, o: Box) => r.x < o.x + o.width && o.x < r.x + r.width && r.y < o.y + o.height && o.y < r.y + r.height
    const labelAt = new Map<string, Point>()
    for (const d of drawn) {
      const lines = linesOf(d)
      const w = Math.max(...lines.map((l) => mono(l.text, LABEL_SIZE))) + 10
      const h = lines.length * 13 + 5
      const s = boundary(box(d.left), at(d.right))
      const e = boundary(box(d.right), at(d.left))
      const spot = (t: number) => ({ x: s.x + (e.x - s.x) * t, y: s.y + (e.y - s.y) * t })
      const rect = (p: Point): Box => ({ x: p.x - w / 2 - 2, y: p.y - h / 2 - 2, width: w + 4, height: h + 4 })
      const t = [0.5, 0.4, 0.6, 0.3, 0.7, 0.2, 0.8].find((t) => {
        const r = rect(spot(t))
        return !classBoxes.some((b) => hit(r, b)) && !placed.some((b) => hit(r, b))
      })
      const p = spot(t ?? 0.5)
      placed.push(rect(p))
      labelAt.set(d.key, p)
    }
    labels
      .transition(T)
      .attr('opacity', (d) => (dimmedLink(d.a, d.b) ? 0 : 1))
      .attr('transform', (d) => `translate(${labelAt.get(d.key)!.x},${labelAt.get(d.key)!.y})`)

    // Self-relations: a loop on top of the class, named above it.
    const loops = g
      .select('g.loops')
      .selectAll<SVGGElement, [string, Rel[]]>('g.loop')
      .data([...view.loops], (d) => d[0])
      .join(
        (enter) => {
          const e = enter.append('g').attr('class', 'loop').attr('opacity', 0)
          e.append('path').attr('fill', 'none')
          e.append('text').attr('font-family', 'ui-monospace, monospace').attr('font-size', LABEL_SIZE).attr('text-anchor', 'middle')
          return e
        },
        (update) => update,
        (exit) => exit.transition(T).attr('opacity', 0).remove(),
      )
    loops
      .select('path')
      .style('stroke', ([, rels]) => COLOR[groupStatus(rels)])
      .attr('stroke-width', 1.25)
      .attr('marker-end', ([, rels]) => `url(#${uid}-arrow-${groupStatus(rels)})`)
      .attr('d', ([l]) => {
        const b = box(l)
        const cx = b.x + b.width / 2
        return `M${cx - 14},${b.y - 2} C${cx - 18},${b.y - 30} ${cx + 18},${b.y - 30} ${cx + 12},${b.y - 5}`
      })
    loops
      .select('text')
      .attr('x', ([l]) => at(l).x)
      .attr('y', ([l]) => box(l).y - 30)
      .style('fill', 'var(--foreground)')
      .text(([, rels]) => rels.map((r) => r.relation).join(', '))
    loops.transition(T).attr('opacity', ([l]) => (dimmedClass(l) ? 0.12 : 1))

    // Classes.
    const nodes = g
      .select('g.nodes')
      .selectAll<SVGGElement, ClassItem>('g.node')
      .data(view.classes, (d) => d.label)
      .join(
        (enter) => {
          const e = enter
            .append('g')
            .attr('class', 'node')
            .attr('opacity', 0)
            .attr('transform', (d) => `translate(${box(d.label).x},${box(d.label).y})`)
            .style('cursor', 'pointer')
          e.append('rect').attr('rx', 7)
          e.append('text').attr('class', 'name').attr('font-family', 'ui-monospace, monospace').attr('font-size', NAME_SIZE).attr('font-weight', 600)
          e.append('text').attr('class', 'count').attr('font-family', 'ui-monospace, monospace').attr('font-size', 10).attr('text-anchor', 'end')
          e.append('title')
          return e
        },
        (update) => update,
        (exit) => exit.transition(T).attr('opacity', 0).remove(),
      )
      .on('mouseenter', (_, d) => setHover(d.label))
      .on('mouseleave', () => setHover(null))
      .on('click', (e: MouseEvent, d) => {
        e.stopPropagation()
        onSelect(d.label === selected ? null : d.label)
      })
    nodes
      .select('rect')
      .attr('width', (d) => sizeOf(d.label).width)
      .attr('height', (d) => sizeOf(d.label).height)
      .style('fill', 'var(--card)')
      .style('stroke', (d) =>
        d.label === selected ? 'var(--foreground)' : d.status !== 'kept' ? COLOR[d.status] : matches.has(d.label) ? 'var(--primary)' : 'var(--border)',
      )
      .attr('stroke-width', (d) => (d.label === selected || d.status !== 'kept' || matches.has(d.label) ? 2 : 1))
      .attr('stroke-dasharray', (d) => (d.status === 'removed' ? '4 3' : null))
    nodes
      .select('text.name')
      .attr('x', 12)
      .attr('y', 20.5)
      .style('fill', (d) => (d.deprecated || d.status === 'removed' ? 'var(--muted-foreground)' : 'var(--foreground)'))
      .style('text-decoration', (d) => (d.deprecated || d.status === 'removed' ? 'line-through' : null))
      .text((d) => d.label)
    nodes
      .select('text.count')
      .attr('x', (d) => sizeOf(d.label).width - 10)
      .attr('y', 20)
      .style('fill', 'var(--muted-foreground)')
      .text((d) => {
        const n = d.attributes.length + d.inherited.length
        return n ? String(n) : ''
      })
    nodes.select('title').text((d) => `${d.label} · ${d.attributes.length} attributes${d.inherited.length ? ` (+${d.inherited.length} inherited)` : ''}`)
    nodes
      .transition(T)
      .attr('transform', (d) => `translate(${box(d.label).x},${box(d.label).y})`)
      .attr('opacity', (d) => (dimmedClass(d.label) ? 0.2 : d.status === 'removed' ? 0.6 : 1))
  }, [view, positions, sizeOf, hover, selected, query, onSelect, uid])

  const markers = (['kept', 'added', 'removed'] as const).map((s) => (
    <marker key={s} id={`${uid}-arrow-${s}`} viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
      <path d="M0,0 L10,5 L0,10 z" style={{ fill: COLOR[s] }} />
    </marker>
  ))
  return (
    <>
      <svg ref={svgRef} className="size-full select-none" onClick={() => onSelect(null)}>
        <defs>
          {markers}
          <marker id={`${uid}-tri`} viewBox="0 0 12 12" refX="11" refY="6" markerWidth="11" markerHeight="11" orient="auto">
            <path d="M1,1 L11,6 L1,11 z" style={{ fill: 'var(--background)', stroke: 'var(--muted-foreground)' }} />
          </marker>
        </defs>
        <g ref={gRef}>
          <g className="subclass" />
          <g className="bundles" />
          <g className="loops" />
          <g className="nodes" />
          <g className="labels" style={{ pointerEvents: 'none' }} />
        </g>
      </svg>
      <Legend />
    </>
  )
}

function Legend() {
  return (
    <div className="pointer-events-none absolute top-2 left-2 flex flex-wrap gap-x-3 rounded border bg-background/90 px-2 py-1 text-[11px] text-muted-foreground">
      <span>
        <span className="font-mono text-foreground">REL →</span> relation, read left to right
      </span>
      <span>╌▷ subclass of</span>
      <span>n attributes</span>
      <span className="text-diff-additive">added</span>
      <span className="text-diff-breaking line-through">removed</span>
      <span>scroll to zoom · hover to focus · click for details</span>
    </div>
  )
}

