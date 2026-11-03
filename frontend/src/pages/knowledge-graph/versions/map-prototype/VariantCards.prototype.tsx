/**
 * PROTOTYPE variant B, "Schema cards": an ERD. Each class is a card listing its
 * attributes (`*` required, type or Vocabulary) and then its outgoing relations, one row
 * each; every relation's line leaves from its own row, so a line's name is read where it
 * starts rather than on a label floating mid-canvas. Subclass links run up from the
 * card's top to its superclass, dashed with a hollow triangle. Each card is sized for the
 * largest it ever is across the history, so cards keep their place in every version.
 */
import { useEffect, useId, useRef, useState } from 'react'
import { linkHorizontal, linkVertical, select, zoom, zoomIdentity } from 'd3'
import { cn } from '@/lib/utils'
import type { VariantProps } from './variants.prototype'
import { HEADER, MAX_ATTRS, ROW } from './sizes.prototype'
import type { Status } from './schema-view.prototype'
import { boundsOf } from './stable-layout.prototype'


const COLOR: Record<Status, string> = {
  kept: 'var(--muted-foreground)',
  added: 'var(--diff-additive)',
  removed: 'var(--diff-breaking)',
}


const hLink = linkHorizontal<{ source: [number, number]; target: [number, number] }, [number, number]>()
const vLink = linkVertical<{ source: [number, number]; target: [number, number] }, [number, number]>()

export function VariantCards({ view, positions, sizeOf, query, selected, onSelect }: VariantProps) {
  const svgRef = useRef<SVGSVGElement>(null)
  const gRef = useRef<SVGGElement>(null)
  const [hover, setHover] = useState<string | null>(null)
  const uid = useId().replace(/[^a-zA-Z0-9]/g, '')

  useEffect(() => {
    const svg = select(svgRef.current!)
    const g = select(gRef.current!)
    const z = zoom<SVGSVGElement, unknown>()
      .scaleExtent([0.1, 3])
      .on('zoom', (e) => g.attr('transform', e.transform.toString()))
    svg.call(z).on('dblclick.zoom', null)
    const { width, height } = svgRef.current!.getBoundingClientRect()
    const b = boundsOf(positions, sizeOf)
    const k = Math.min(1, 0.92 * Math.min(width / (b.x1 - b.x0 + 80), height / (b.y1 - b.y0 + 80)))
    svg.call(z.transform, zoomIdentity.translate(width / 2, height / 2).scale(k).translate(-(b.x0 + b.x1) / 2, -(b.y0 + b.y1) / 2))
    return () => {
      svg.on('.zoom', null)
    }
  }, [positions, sizeOf])

  const top = (l: string) => {
    const p = positions.get(l) ?? { x: 0, y: 0 }
    const s = sizeOf(l)
    return { x: p.x - s.width / 2, y: p.y - s.height / 2, ...s }
  }
  const focus = hover ?? selected
  const q = query.trim().toLowerCase()
  const isMatch = (l: string) =>
    !!q &&
    (l.toLowerCase().includes(q) || !!view.byLabel.get(l)?.attributes.some((a) => a.name.toLowerCase().includes(q)))
  const near = new Set<string>(focus ? [focus] : [])
  if (focus)
    for (const r of view.rels) if (r.source === focus || r.target === focus) near.add(r.source).add(r.target)
  if (focus) for (const s of view.subclass) if (s.child === focus || s.parent === focus) near.add(s.child).add(s.parent)
  const dim = (l: string) => (focus ? !near.has(l) : q ? !isMatch(l) : false)
  const dimLink = (a: string, b: string) => (focus ? a !== focus && b !== focus : q ? !isMatch(a) && !isMatch(b) : false)

  // Each card's rows, and the y of each outgoing relation's row, to start its line there.
  const cards = view.classes.map((c) => {
    const attrs = c.attributes.slice(0, MAX_ATTRS)
    const more = c.attributes.length - attrs.length
    const out = view.rels.filter((r) => r.source === c.label)
    const firstRel = attrs.length + (more > 0 ? 1 : 0)
    return { c, attrs, more, out, firstRel }
  })
  const rowY = (b: { y: number }, i: number) => b.y + HEADER + i * ROW + ROW / 2 + 3

  const edges = cards.flatMap(({ c, out, firstRel }) =>
    out
      .filter((r) => r.target !== r.source)
      .map((r, i) => {
        const [s, t] = [top(c.label), top(r.target)]
        const y = rowY(s, firstRel + i)
        const rightward = t.x + t.width / 2 >= s.x + s.width / 2
        const sx = rightward ? s.x + s.width : s.x
        // Into the target's near side, at its header.
        const tx = rightward ? (t.x > sx ? t.x : t.x + t.width) : t.x + t.width < sx ? t.x + t.width : t.x
        const ty = t.y + HEADER / 2
        return { r, d: hLink({ source: [sx, y], target: [tx + (tx > sx ? -6 : 6), ty] })! }
      }),
  )

  return (
    <svg ref={svgRef} className="size-full select-none" onClick={() => onSelect(null)}>
      <defs>
        {(['kept', 'added', 'removed'] as const).map((s) => (
          <marker key={s} id={`${uid}-a-${s}`} viewBox="0 0 10 10" refX="1" refY="5" markerWidth="6" markerHeight="6" orient="auto">
            <path d="M0,0 L10,5 L0,10 z" style={{ fill: COLOR[s] }} />
          </marker>
        ))}
        <marker id={`${uid}-tri`} viewBox="0 0 12 12" refX="11" refY="6" markerWidth="11" markerHeight="11" orient="auto">
          <path d="M1,1 L11,6 L1,11 z" style={{ fill: 'var(--background)', stroke: 'var(--muted-foreground)' }} />
        </marker>
      </defs>
      <g ref={gRef}>
        {view.subclass.map((s) => {
          const [c, p] = [top(s.child), top(s.parent)]
          return (
            <path
              key={`${s.child}>${s.parent}`}
              d={vLink({ source: [c.x + c.width / 2, c.y], target: [p.x + p.width / 2, p.y + p.height + 2] })!}
              fill="none"
              strokeDasharray="5 4"
              markerEnd={`url(#${uid}-tri)`}
              style={{ stroke: COLOR[s.status], opacity: dimLink(s.child, s.parent) ? 0.1 : 1, transition: 'opacity .2s' }}
            />
          )
        })}
        {edges.map(({ r, d }) => (
          <path
            key={r.id}
            d={d}
            fill="none"
            strokeWidth={focus && (r.source === focus || r.target === focus) ? 2 : 1.2}
            strokeDasharray={r.status === 'removed' ? '3 3' : undefined}
            markerEnd={`url(#${uid}-a-${r.status})`}
            style={{ stroke: COLOR[r.status], opacity: dimLink(r.source, r.target) ? 0.08 : 0.9, transition: 'opacity .2s' }}
          />
        ))}
        {cards.map(({ c, attrs, more, out, firstRel }) => {
          const b = top(c.label)
          const ring =
            c.label === selected ? 'var(--foreground)' : c.status !== 'kept' ? COLOR[c.status] : isMatch(c.label) ? 'var(--primary)' : 'var(--border)'
          return (
            <g
              key={c.label}
              style={{
                transform: `translate(${b.x}px, ${b.y}px)`,
                transition: 'transform .35s, opacity .2s',
                opacity: dim(c.label) ? 0.2 : c.status === 'removed' ? 0.6 : 1,
                cursor: 'pointer',
              }}
              onMouseEnter={() => setHover(c.label)}
              onMouseLeave={() => setHover(null)}
              onClick={(e) => {
                e.stopPropagation()
                onSelect(c.label === selected ? null : c.label)
              }}
            >
              <rect
                width={b.width}
                height={b.height}
                rx={6}
                strokeWidth={ring === 'var(--border)' ? 1 : 2}
                strokeDasharray={c.status === 'removed' ? '4 3' : undefined}
                style={{ fill: 'var(--card)', stroke: ring }}
              />
              <path d={`M0,${HEADER} H${b.width}`} style={{ stroke: 'var(--border)' }} />
              <text
                x={10}
                y={18.5}
                fontFamily="ui-monospace, monospace"
                fontSize={13}
                fontWeight={600}
                style={{ fill: 'var(--foreground)', textDecoration: c.deprecated || c.status === 'removed' ? 'line-through' : undefined }}
              >
                {c.label}
              </text>
              {c.parent && (
                <text x={b.width - 8} y={18} textAnchor="end" fontSize={10} style={{ fill: 'var(--muted-foreground)' }}>
                  ↑ {c.parent}
                </text>
              )}
              <g fontFamily="ui-monospace, monospace" fontSize={11}>
                {attrs.map((a, i) => (
                  <g key={a.name} transform={`translate(0, ${HEADER + i * ROW + ROW - 1})`}>
                    <text x={10} style={{ fill: 'var(--foreground)' }}>
                      {a.name}
                      {a.required && <tspan style={{ fill: 'var(--diff-deprecating)' }}>*</tspan>}
                    </text>
                    <text x={b.width - 10} textAnchor="end" style={{ fill: 'var(--muted-foreground)' }}>
                      {a.vocabulary ?? a.type}
                    </text>
                  </g>
                ))}
                {more > 0 && (
                  <text x={10} y={HEADER + attrs.length * ROW + ROW - 1} style={{ fill: 'var(--muted-foreground)' }}>
                    +{more} more{c.inherited.length ? ` · ${c.inherited.length} inherited` : ''}
                  </text>
                )}
                {out.length > 0 && firstRel > 0 && (
                  <path d={`M8,${HEADER + firstRel * ROW + 2} H${b.width - 8}`} strokeDasharray="2 3" style={{ stroke: 'var(--border)' }} />
                )}
                {out.map((r, i) => (
                  <text
                    key={r.id}
                    x={10}
                    y={HEADER + (firstRel + i) * ROW + ROW - 1}
                    className={cn(r.status === 'removed' && 'line-through')}
                    style={{ fill: r.status === 'kept' ? 'var(--foreground)' : COLOR[r.status] }}
                  >
                    {r.relation}
                    <tspan style={{ fill: 'var(--muted-foreground)' }}>{r.target === r.source ? ' ↻' : ' → '}</tspan>
                    {r.target !== r.source && r.target}
                  </text>
                ))}
              </g>
            </g>
          )
        })}
      </g>
    </svg>
  )
}
