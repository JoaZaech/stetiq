/**
 * The Ontology Map: an Ontology as a node-link dataset (docs/ontology-view-abstraction.md).
 * Classes are nodes, keyed by label. Each Pattern is a link, keyed by
 * (source, relation, target); relations are not nodes. Each superclass is a subclass
 * link, a separate link type keyed by (child, parent). No React and no I/O here.
 *
 * Its siblings build on it: `ontology-map-comparison` (two versions superimposed),
 * `ontology-map-focus` (selection, details and search), `ontology-map-paths` (shortest
 * paths) and `ontology-map-layout` (where each class goes).
 */
import type { Ontology } from '@/api/ontology-versions'
import { patternId } from './concepts'

export interface MapNode {
  /** The class label, also the node's key. */
  label: string
  deprecated: boolean
}

export interface PatternLink {
  /** `(Source)-[REL]->(Target)`, the syntax of `Pattern.__str__`. */
  id: string
  source: string
  relation: string
  target: string
  /** Whether its relation is deprecated. */
  deprecated: boolean
  route: LinkRoute
}

/**
 * How a link is drawn apart from the others between the same classes.
 *
 * - `line`: from source to target, bent `bend` link spacings to the left of its own
 *   direction (0 is straight). Parallel links, either way round, get distinct bends.
 * - `loop`: a Pattern from a class to itself, drawn as an arc; the n-th loop on a class
 *   has size n, so loops on one class nest instead of overlapping.
 */
export type LinkRoute = { kind: 'line'; bend: number } | { kind: 'loop'; size: number }

/** A class's superclass, drawn from the subclass (child) to the superclass (parent). */
export interface SubclassLink {
  /** `Child -> Parent` */
  id: string
  child: string
  parent: string
}

export interface OntologyMap {
  nodes: MapNode[]
  links: PatternLink[]
  subclassLinks: SubclassLink[]
}

/** An Ontology's classes as nodes and its Patterns as links. */
export function ontologyMap(ontology: Ontology): OntologyMap {
  const nodes = ontology.node_types.map((n) => ({ label: n.label, deprecated: n.deprecated ?? false }))
  const deprecatedRelations = new Set(
    ontology.relationship_types.filter((r) => r.deprecated).map((r) => r.label),
  )
  const patterns = ontology.patterns.map(([source, relation, target]) => ({
    id: patternId([source, relation, target]),
    source,
    relation,
    target,
    deprecated: deprecatedRelations.has(relation),
  }))

  // Links between the same two classes, in either direction, keyed by the pair.
  const between = new Map<string, typeof patterns>()
  for (const p of patterns) {
    const key = JSON.stringify([p.source, p.target].sort())
    between.set(key, [...(between.get(key) ?? []), p])
  }

  const links = patterns.map((p): PatternLink => {
    const siblings = [...between.get(JSON.stringify([p.source, p.target].sort()))!].sort((a, b) =>
      a.id.localeCompare(b.id),
    )
    const index = siblings.indexOf(p)
    if (p.source === p.target) return { ...p, route: { kind: 'loop', size: index + 1 } }
    // Slots are spread around 0 along the pair's alphabetical direction; a link running
    // the other way flips its slot, since its left is that direction's right.
    const slot = index - (siblings.length - 1) / 2
    const bend = p.source < p.target ? slot : -slot
    return { ...p, route: { kind: 'line', bend: bend === 0 ? 0 : bend } } // never -0
  })

  // A superclass the Ontology doesn't declare has no node to link to.
  const labels = new Set(nodes.map((n) => n.label))
  const subclassLinks = ontology.node_types
    .filter((n) => n.parent !== undefined && labels.has(n.parent))
    .map((n) => ({ id: `${n.label} -> ${n.parent}`, child: n.label, parent: n.parent! }))
  return { nodes, links, subclassLinks }
}

/** What the Map leaves out. */
export interface MapFilters {
  /** Hide deprecated classes and relations, and every link to a hidden class. */
  hideDeprecated: boolean
  hideSubclassLinks: boolean
}

/**
 * The Map without what `filters` hide. Links keep their routes, and the layout stays
 * that of the whole Map, so nothing moves when a filter changes.
 */
export function filterOntologyMap(map: OntologyMap, filters: MapFilters): OntologyMap {
  const hidden = new Set(
    filters.hideDeprecated ? map.nodes.filter((n) => n.deprecated).map((n) => n.label) : [],
  )
  const nodes = map.nodes.filter((n) => !hidden.has(n.label))
  const links = map.links.filter(
    (l) => !(filters.hideDeprecated && l.deprecated) && !hidden.has(l.source) && !hidden.has(l.target),
  )
  const subclassLinks = filters.hideSubclassLinks
    ? []
    : map.subclassLinks.filter((l) => !hidden.has(l.child) && !hidden.has(l.parent))
  return { nodes, links, subclassLinks }
}
