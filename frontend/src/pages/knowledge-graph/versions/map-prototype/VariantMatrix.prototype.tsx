/**
 * PROTOTYPE variant C, "Matrix": classes × classes, a row's class the source and a
 * column's the target of the relations in their cell. No lines, so nothing crosses or
 * overlaps at any size; parallel relations are a count in one cell. Rows are the
 * subclass tree (indented under the superclass), siblings ordered by where the anchored
 * Map places them, so linked classes sit close and blocks show communities. Every class
 * of the history keeps its row in every version (faint where this version lacks it), so
 * the matrix is the same grid for every version.
 */
import { useMemo, useState } from 'react'
import { scaleBand } from 'd3'
import { cn } from '@/lib/utils'
import type { VariantProps } from './variants.prototype'
import { mono, type Rel, type Status } from './schema-view.prototype'
import { unionOntology } from './stable-layout.prototype'

const CELL = 22
const TOP = 140

const FILL: Record<Status, string> = {
  kept: 'var(--foreground)',
  added: 'var(--diff-additive)',
  removed: 'var(--diff-breaking)',
}

export function VariantMatrix({ view, history, positions, query, selected, onSelect }: VariantProps) {
  const [keepSlots, setKeepSlots] = useState(true)
  const [hover, setHover] = useState<{ row?: string; col?: string } | null>(null)

  // The subclass tree of every class the history has, siblings in layout order (x, then y).
  const order = useMemo(() => {
    const union = unionOntology(history)
    const labels = new Set(union.node_types.map((n) => n.label))
    const children = new Map<string | undefined, string[]>()
    for (const n of union.node_types) {
      const parent = n.parent && labels.has(n.parent) ? n.parent : undefined
      children.set(parent, [...(children.get(parent) ?? []), n.label])
    }
    const pos = (l: string) => positions.get(l) ?? { x: 0, y: 0 }
    const out: { label: string; depth: number }[] = []
    const seen = new Set<string>()
    const walk = (parent: string | undefined, depth: number) => {
      const kids = [...(children.get(parent) ?? [])].sort((a, b) => pos(a).x - pos(b).x || pos(a).y - pos(b).y)
      for (const k of kids) {
        if (seen.has(k)) continue
        seen.add(k)
        out.push({ label: k, depth })
        walk(k, depth + 1)
      }
    }
    walk(undefined, 0)
    return out
  }, [history, positions])

  const rows = keepSlots ? order : order.filter((r) => view.byLabel.has(r.label))
  const left = Math.max(160, ...rows.map((r) => mono(r.label, 12) + r.depth * 12 + 44))
  const band = scaleBand<string>()
    .domain(rows.map((r) => r.label))
    .range([0, rows.length * CELL])
  const cells = new Map<string, Rel[]>()
  for (const r of view.rels) {
    const k = `${r.source}|${r.target}`
    cells.set(k, [...(cells.get(k) ?? []), r])
  }
  const q = query.trim().toLowerCase()
  const isMatch = (l: string) => !!q && l.toLowerCase().includes(q)
  const focusRow = hover?.row ?? selected ?? undefined
  const focusCol = hover?.col ?? selected ?? undefined

  const readout = (() => {
    if (hover?.row && hover?.col) {
      const rels = cells.get(`${hover.row}|${hover.col}`) ?? []
      return rels.length === 0
        ? `${hover.row} → ${hover.col}: no relation`
        : rels.map((r) => `(${r.source})-[${r.relation}]->(${r.target})${r.status === 'kept' ? '' : ` · ${r.status}`}`).join('   ')
    }
    const l = hover?.row ?? hover?.col ?? selected
    if (!l) return 'Row: source class · column: target class · hover a cell for its relations · click a class for details'
    const c = view.byLabel.get(l)
    if (!c) return `${l}: not in this version`
    const out = view.rels.filter((r) => r.source === l).length
    const inc = view.rels.filter((r) => r.target === l).length
    return `${l}${c.parent ? ` ⊂ ${c.parent}` : ''} · ${c.attributes.length} attributes${c.inherited.length ? ` (+${c.inherited.length} inherited)` : ''} · ${out} out · ${inc} in`
  })()

  const width = left + rows.length * CELL + 20
  const height = TOP + rows.length * CELL + 20
  return (
    <div className="flex size-full flex-col">
      <div className="flex items-center gap-4 border-b px-3 py-1.5 text-xs">
        <span className="min-w-0 flex-1 truncate font-mono">{readout}</span>
        <label className="flex shrink-0 items-center gap-1.5 text-muted-foreground">
          <input type="checkbox" checked={keepSlots} onChange={(e) => setKeepSlots(e.target.checked)} />
          Keep rows of classes from other versions
        </label>
      </div>
      <div className="min-h-0 flex-1 overflow-auto" onMouseLeave={() => setHover(null)}>
        <svg width={width} height={height} className="select-none" fontFamily="ui-monospace, monospace">
          <g transform={`translate(${left}, ${TOP})`}>
            {/* Crosshair bands. */}
            {focusRow && band(focusRow) !== undefined && (
              <rect x={-left} y={band(focusRow)} width={left + rows.length * CELL} height={CELL} style={{ fill: 'var(--accent)' }} />
            )}
            {focusCol && band(focusCol) !== undefined && (
              <rect x={band(focusCol)} y={-TOP} width={CELL} height={TOP + rows.length * CELL} style={{ fill: 'var(--accent)' }} />
            )}
            {/* Grid. */}
            {rows.map((r) => (
              <g key={r.label}>
                <path d={`M0,${band(r.label)! + CELL} H${rows.length * CELL}`} style={{ stroke: 'var(--border)' }} />
                <path d={`M${band(r.label)! + CELL},0 V${rows.length * CELL}`} style={{ stroke: 'var(--border)' }} />
                <rect x={band(r.label)} y={band(r.label)} width={CELL} height={CELL} style={{ fill: 'var(--muted)' }} />
              </g>
            ))}
            <path d={`M0,0 H${rows.length * CELL} M0,0 V${rows.length * CELL}`} style={{ stroke: 'var(--border)' }} />
            {/* Row and column headers. */}
            {rows.map((r) => {
              const c = view.byLabel.get(r.label)
              const absent = !c
              const statusFill = c && c.status !== 'kept' ? FILL[c.status] : absent ? 'var(--muted-foreground)' : 'var(--foreground)'
              const common = {
                onMouseEnter: () => setHover({ row: r.label }),
                onClick: () => !absent && onSelect(r.label === selected ? null : r.label),
                style: {
                  fill: statusFill,
                  opacity: absent ? 0.35 : 1,
                  cursor: absent ? 'default' : 'pointer',
                  textDecoration: c?.status === 'removed' || c?.deprecated ? 'line-through' : undefined,
                  fontWeight: r.label === selected || isMatch(r.label) ? 700 : 400,
                },
              }
              const attrs = c ? c.attributes.length + c.inherited.length : 0
              return (
                <g key={r.label}>
                  <text {...common} x={-left + 8 + r.depth * 12} y={band(r.label)! + 15} fontSize={12}>
                    {r.depth > 0 ? '└ ' : ''}
                    {r.label}
                  </text>
                  {attrs > 0 && (
                    <text x={-8} y={band(r.label)! + 15} textAnchor="end" fontSize={10} style={{ fill: 'var(--muted-foreground)' }}>
                      {attrs}
                    </text>
                  )}
                  <text
                    {...common}
                    onMouseEnter={() => setHover({ col: r.label })}
                    transform={`translate(${band(r.label)! + CELL / 2 + 4}, -6) rotate(-55)`}
                    fontSize={11}
                  >
                    {r.label}
                  </text>
                </g>
              )
            })}
            {/* Cells. */}
            {rows.flatMap((row) =>
              rows.map((col) => {
                const rels = cells.get(`${row.label}|${col.label}`)
                const x = band(col.label)!
                const y = band(row.label)!
                const status: Status = !rels
                  ? 'kept'
                  : rels.every((r) => r.status === 'added')
                    ? 'added'
                    : rels.every((r) => r.status === 'removed')
                      ? 'removed'
                      : 'kept'
                const dimmed = (q && !isMatch(row.label) && !isMatch(col.label)) || (selected && row.label !== selected && col.label !== selected)
                return (
                  <g key={`${row.label}|${col.label}`} onMouseEnter={() => setHover({ row: row.label, col: col.label })}>
                    <rect x={x} y={y} width={CELL} height={CELL} fill="transparent" />
                    {rels && (
                      <>
                        <rect
                          x={x + 3}
                          y={y + 3}
                          width={CELL - 6}
                          height={CELL - 6}
                          rx={3}
                          className={cn('transition-opacity', dimmed && 'opacity-20')}
                          strokeWidth={1.5}
                          strokeDasharray={status === 'removed' ? '2 2' : undefined}
                          style={{
                            fill: status === 'removed' ? 'transparent' : FILL[status],
                            stroke: FILL[status],
                            fillOpacity: status === 'kept' ? 0.75 : 1,
                          }}
                        />
                        {rels.length > 1 && (
                          <text
                            x={x + CELL / 2}
                            y={y + 15}
                            textAnchor="middle"
                            fontSize={10}
                            fontWeight={700}
                            style={{ fill: status === 'removed' ? FILL.removed : 'var(--background)', pointerEvents: 'none' }}
                          >
                            {rels.length}
                          </text>
                        )}
                      </>
                    )}
                  </g>
                )
              }),
            )}
          </g>
        </svg>
      </div>
    </div>
  )
}
