/** PROTOTYPE (branch prototype/ontology-map-d3): how big each variant draws a class, over the whole history. */
import type { Ontology } from '@/api/ontology-versions'
import { mono } from './schema-view.prototype'
import type { Size } from './stable-layout.prototype'

export const NAME_SIZE = 13
export const HEADER = 28
export const ROW = 16
export const MAX_ATTRS = 8

export const anchoredSizeOf = (history: Ontology[]) => {
  const attrs = new Map<string, number>()
  for (const o of history) for (const n of o.node_types) attrs.set(n.label, Math.max(attrs.get(n.label) ?? 0, (n.properties ?? []).length))
  return (label: string): Size => ({
    width: Math.max(110, mono(label, NAME_SIZE) + 24 + (attrs.get(label) ? 26 : 0)),
    height: 32,
  })
}

export const cardSizeOf = (history: Ontology[]) => {
  const sizes = new Map<string, Size>()
  for (const o of history) {
    for (const n of o.node_types) {
      const attrs = (n.properties ?? []).map((a) => `${a.name}* ${a.vocabulary ?? a.type}`)
      const rels = o.patterns.filter(([s]) => s === n.label).map(([, r, t]) => `${r} → ${t}`)
      const rows = Math.min(attrs.length, MAX_ATTRS) + (attrs.length > MAX_ATTRS ? 1 : 0) + rels.length
      const width = Math.min(300, Math.max(180, mono(n.label, 13) + 30, ...[...attrs, ...rels].map((t) => mono(t, 11) + 28)))
      const height = HEADER + Math.max(1, rows) * ROW + 10
      const prev = sizes.get(n.label)
      sizes.set(n.label, { width: Math.max(width, prev?.width ?? 0), height: Math.max(height, prev?.height ?? 0) })
    }
  }
  return (label: string) => sizes.get(label) ?? { width: 180, height: 60 }
}
