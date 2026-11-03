/**
 * PROTOTYPE (throwaway, branch prototype/ontology-map-d3): what each variant draws for
 * one Ontology Version: its classes with their own and inherited attributes, its
 * Patterns grouped into one bundle per class pair (so parallel relations never pile up),
 * and, against the previous version, what was added or removed.
 */
import { randomLcg } from 'd3'
import type { Ontology, OntologyConcept, OntologyProperty } from '@/api/ontology-versions'

export type Status = 'kept' | 'added' | 'removed'

export interface ClassItem {
  label: string
  parent?: string
  deprecated: boolean
  definition?: string
  attributes: OntologyProperty[]
  /** Attributes from superclasses, with the class they come from. */
  inherited: (OntologyProperty & { from: string })[]
  status: Status
}

export interface Rel {
  id: string
  relation: string
  source: string
  target: string
  deprecated: boolean
  status: Status
}

/** Every Pattern between two different classes, either way round. `a` < `b`. */
export interface Bundle {
  key: string
  a: string
  b: string
  relations: Rel[]
}

export interface SubclassItem {
  child: string
  parent: string
  status: Status
}

export interface SchemaView {
  classes: ClassItem[]
  byLabel: Map<string, ClassItem>
  bundles: Bundle[]
  /** Self-relations by class. */
  loops: Map<string, Rel[]>
  subclass: SubclassItem[]
  rels: Rel[]
  counts: { classes: number; patterns: number; added: number; removed: number }
}

const relId = ([s, r, t]: [string, string, string]) => `(${s})-[${r}]->(${t})`

function inheritedOf(o: Ontology, label: string) {
  const byLabel = new Map(o.node_types.map((n) => [n.label, n]))
  const out: (OntologyProperty & { from: string })[] = []
  const seen = new Set([label])
  let parent = byLabel.get(label)?.parent
  while (parent && !seen.has(parent) && byLabel.has(parent)) {
    seen.add(parent)
    const p = byLabel.get(parent)!
    out.push(...(p.properties ?? []).map((a) => ({ ...a, from: parent! })))
    parent = p.parent
  }
  return out
}

/** `current` as the variants draw it; with `previous`, also what changed since (removed ones as ghosts). */
export function schemaView(current: Ontology, previous?: Ontology, showRemoved = true): SchemaView {
  const prevClasses = new Set(previous?.node_types.map((n) => n.label) ?? [])
  const curClasses = new Set(current.node_types.map((n) => n.label))
  const prevRels = new Set(previous?.patterns.map(relId) ?? [])
  const curRels = new Set(current.patterns.map(relId))
  const status = (inCur: boolean, inPrev: boolean): Status =>
    !previous ? 'kept' : inCur && inPrev ? 'kept' : inCur ? 'added' : 'removed'

  const deprecatedRel = new Set(
    [...current.relationship_types, ...(previous?.relationship_types ?? [])].filter((r) => r.deprecated).map((r) => r.label),
  )
  const toClass = (o: Ontology, n: OntologyConcept, s: Status): ClassItem => ({
    label: n.label,
    parent: n.parent,
    deprecated: n.deprecated ?? false,
    definition: n.definition,
    attributes: n.properties ?? [],
    inherited: inheritedOf(o, n.label),
    status: s,
  })
  const classes = current.node_types.map((n) => toClass(current, n, status(true, prevClasses.has(n.label))))
  if (previous && showRemoved)
    for (const n of previous.node_types) if (!curClasses.has(n.label)) classes.push(toClass(previous, n, 'removed'))
  const byLabel = new Map(classes.map((c) => [c.label, c]))

  const toRel = (p: [string, string, string], s: Status): Rel => ({
    id: relId(p),
    relation: p[1],
    source: p[0],
    target: p[2],
    deprecated: deprecatedRel.has(p[1]),
    status: s,
  })
  const rels = current.patterns.map((p) => toRel(p, status(true, prevRels.has(relId(p)))))
  if (previous && showRemoved)
    for (const p of previous.patterns) if (!curRels.has(relId(p))) rels.push(toRel(p, 'removed'))
  const drawable = rels.filter((r) => byLabel.has(r.source) && byLabel.has(r.target))

  const bundles = new Map<string, Bundle>()
  const loops = new Map<string, Rel[]>()
  for (const r of drawable) {
    if (r.source === r.target) {
      loops.set(r.source, [...(loops.get(r.source) ?? []), r])
      continue
    }
    const [a, b] = [r.source, r.target].sort()
    const key = `${a}|${b}`
    const bundle = bundles.get(key) ?? { key, a, b, relations: [] }
    bundle.relations.push(r)
    bundles.set(key, bundle)
  }
  for (const b of bundles.values()) b.relations.sort((x, y) => x.relation.localeCompare(y.relation))

  const subclass: SubclassItem[] = classes
    .filter((c) => c.parent && byLabel.has(c.parent))
    .map((c) => {
      const prevParent = previous?.node_types.find((n) => n.label === c.label)?.parent
      const s: Status = c.status === 'removed' ? 'removed' : previous && prevParent !== c.parent ? 'added' : 'kept'
      return { child: c.label, parent: c.parent!, status: s }
    })

  return {
    classes,
    byLabel,
    bundles: [...bundles.values()],
    loops,
    subclass,
    rels: drawable,
    counts: {
      classes: current.node_types.length,
      patterns: current.patterns.length,
      added: classes.filter((c) => c.status === 'added').length + rels.filter((r) => r.status === 'added').length,
      removed: classes.filter((c) => c.status === 'removed').length + rels.filter((r) => r.status === 'removed').length,
    },
  }
}

/** Monospace text width at `size` px. */
export const mono = (text: string, size: number) => Math.ceil(text.length * size * 0.62)

// ---------------------------------------------------------------------------------------
// A synthetic, production-sized Knowledge Graph: 5 versions, ~50 → ~80 classes.

const NOUNS =
  'Asset Site Plant Line Machine Component Sensor Reading Alarm WorkOrder Task Technician Crew Shift Supplier Part Stock Warehouse Bin Purchase Invoice Customer Contract Project Document Drawing Revision Inspection Finding Defect Cause Action Permit Hazard Risk Control Audit Standard Clause Training Course Certificate Skill Team Department Location Room Building Floor Zone Meter Tariff Budget CostCenter Vendor Shipment Carrier Route Stop Vehicle Driver Trip Fuel Battery Charger Firmware Device Gateway Network Ticket Incident Problem Change Release Service Sla Report Dashboard Kpi Target Forecast Scenario Model Dataset Pipeline Job Schedule Calendar Holiday Event'.split(
    ' ',
  )
const VERBS =
  'HAS_PART LOCATED_IN MEASURES RAISES ASSIGNED_TO PERFORMS SUPPLIES STORES ORDERS BILLS OWNS REFERENCES REVISES INSPECTS FINDS CAUSED_BY RESOLVES REQUIRES MITIGATES COMPLIES_WITH CERTIFIES MEMBER_OF REPORTS_TO CONTAINS FEEDS SCHEDULES DEPENDS_ON REPLACES MONITORS TRIGGERS'.split(
    ' ',
  )
const ATTRS: [string, string][] = [
  ['id', 'STRING'],
  ['name', 'STRING'],
  ['status', 'STRING'],
  ['code', 'STRING'],
  ['createdAt', 'DATE_TIME'],
  ['description', 'STRING'],
  ['amount', 'FLOAT'],
  ['startDate', 'DATE'],
  ['endDate', 'DATE'],
  ['priority', 'INTEGER'],
  ['active', 'BOOLEAN'],
  ['weight', 'FLOAT'],
]

export function syntheticVersions(): { number: number; ontology: Ontology }[] {
  const rand = randomLcg(42)
  const int = (n: number) => Math.floor(rand() * n)
  const attrs = (): OntologyProperty[] =>
    ATTRS.filter((_, i) => i < 2 || rand() < 0.35).map(([name, type], i) => ({
      name,
      type,
      ...(i === 0 || rand() < 0.2 ? { required: true } : {}),
    }))
  let next = 0
  let classes: OntologyConcept[] = []
  let patterns: [string, string, string][] = []
  const addClass = () => {
    const label = NOUNS[next]
    // Community structure: link to a recent class, so the graph has neighbourhoods.
    const near = () => classes[Math.max(0, classes.length - 1 - int(10))]?.label
    const parent = classes.length > 6 && rand() < 0.18 ? near() : undefined
    classes.push({ label, properties: attrs(), ...(parent ? { parent } : {}) })
    const links = parent ? int(2) : 1 + int(2)
    for (let i = 0; i < links; i++) {
      const other = rand() < 0.8 ? near() : classes[int(classes.length)].label
      if (other && other !== label)
        patterns.push(rand() < 0.5 ? [label, VERBS[int(VERBS.length)], other] : [other, VERBS[int(VERBS.length)], label])
    }
    if (rand() < 0.04) patterns.push([label, 'REPLACES', label])
    next++
  }
  for (let i = 0; i < 50; i++) addClass()
  const out: { number: number; ontology: Ontology }[] = []
  const snapshot = () => {
    const used = [...new Set(patterns.map((p) => p[1]))].sort()
    out.push({
      number: out.length + 1,
      ontology: {
        node_types: classes.map((c) => ({ ...c })),
        relationship_types: used.map((label) => ({ label })),
        patterns: [...patterns],
      },
    })
  }
  snapshot()
  for (let v = 2; v <= 5; v++) {
    // Drop two leaf classes, add eight, and a few new Patterns between existing classes.
    for (let i = 0; i < 2; i++) {
      const parents = new Set(classes.map((c) => c.parent))
      const leaves = classes.filter((c) => !parents.has(c.label))
      const gone = leaves[int(leaves.length)].label
      classes = classes.filter((c) => c.label !== gone)
      patterns = patterns.filter(([s, , t]) => s !== gone && t !== gone)
    }
    for (let i = 0; i < 8; i++) addClass()
    for (let i = 0; i < 3; i++) {
      const a = classes[int(classes.length)].label
      const b = classes[int(classes.length)].label
      if (a !== b) patterns.push([a, VERBS[int(VERBS.length)], b])
    }
    snapshot()
  }
  return out
}
