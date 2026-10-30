/**
 * The Ontology Map: an Ontology as a node-link dataset (docs/ontology-view-abstraction.md).
 * Classes are nodes, keyed by label. Each Pattern is a link, keyed by
 * (source, relation, target); relations are not nodes. Each superclass is a subclass
 * link, a separate link type keyed by (child, parent). No React and no I/O here.
 */
import ELK from 'elkjs/lib/elk.bundled.js'
import type { Ontology, OntologyConcept, OntologyProperty } from '@/api/ontology-versions'
import { conceptTables, searchConcepts } from './concepts'

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
    id: `(${source})-[${relation}]->(${target})`,
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

/** The classes and links next to one class, each sorted. */
export interface Neighbourhood {
  /** Classes linked to it, in either direction; not the class itself. */
  classes: string[]
  /** Link ids of the links in and out of it, its self-loops included. */
  links: string[]
}

/** What a class connects to: its outgoing and incoming Pattern links and the classes at their other end. */
export function neighboursOf(map: OntologyMap, label: string): Neighbourhood {
  const links = map.links.filter((l) => l.source === label || l.target === label)
  const classes = new Set(links.flatMap((l) => [l.source, l.target]))
  classes.delete(label)
  return { classes: [...classes].sort(), links: links.map((l) => l.id).sort() }
}

/** What is selected on the Map: one class, by label, or one Pattern link, by id. */
export type MapSelection = { kind: 'class'; label: string } | { kind: 'link'; id: string }

/** The classes and links a selection keeps in focus; the rest of the Map fades. */
export interface MapFocus {
  classes: Set<string>
  links: Set<string>
}

/**
 * What stays in focus for a selection: a class with its neighbours and the links to them,
 * or a link with the two classes it joins. Null when nothing (that still exists) is
 * selected, so nothing fades.
 */
export function focusOf(map: OntologyMap, selection: MapSelection | null): MapFocus | null {
  if (selection?.kind === 'class') {
    if (!map.nodes.some((n) => n.label === selection.label)) return null
    const { classes, links } = neighboursOf(map, selection.label)
    return { classes: new Set([selection.label, ...classes]), links: new Set(links) }
  }
  if (selection?.kind === 'link') {
    const link = map.links.find((l) => l.id === selection.id)
    if (!link) return null
    return { classes: new Set([link.source, link.target]), links: new Set([link.id]) }
  }
  return null
}

/** A property as the details panel lists it. */
export interface DetailProperty {
  name: string
  type: string
  description?: string
  required: boolean
  /** The ancestor class that declares it, when the class inherits it; absent when its own. */
  inheritedFrom?: string
}

export interface ClassDetails {
  kind: 'class'
  label: string
  description?: string
  deprecated: boolean
  parent?: string
  /** Its own properties, then each ancestor's, nearest first; a redeclared one is listed once, as the nearest. */
  properties: DetailProperty[]
  /** Constraints declared on the class, e.g. `UNIQUENESS (name)`. */
  constraints: string[]
}

export interface LinkDetails {
  kind: 'link'
  id: string
  source: string
  relation: string
  target: string
  /** The relation's description, deprecation and properties: every Pattern of a relation shares them. */
  description?: string
  deprecated: boolean
  properties: DetailProperty[]
}

/** What the details panel shows for a selection. */
export type MapDetails = ClassDetails | LinkDetails

const detailProperty = (p: OntologyProperty, inheritedFrom?: string): DetailProperty => ({
  name: p.name,
  type: p.type,
  description: p.description,
  required: p.required ?? false,
  ...(inheritedFrom !== undefined && { inheritedFrom }),
})

/**
 * The details of a selected class or link, or null when nothing (that the Ontology has)
 * is selected. A class's inherited properties come from its superclass chain, which stops
 * at a superclass the Ontology does not declare and never revisits a class.
 */
export function detailsOf(ontology: Ontology, selection: MapSelection | null): MapDetails | null {
  if (selection?.kind === 'class') {
    const classes = new Map(ontology.node_types.map((n) => [n.label, n]))
    const node = classes.get(selection.label)
    if (!node) return null
    const properties: DetailProperty[] = []
    const seen = new Set<string>()
    let c: OntologyConcept | undefined = node
    while (c && !seen.has(c.label)) {
      seen.add(c.label)
      for (const p of c.properties ?? []) {
        if (properties.some((q) => q.name === p.name)) continue
        properties.push(detailProperty(p, c === node ? undefined : c.label))
      }
      c = c.parent === undefined ? undefined : classes.get(c.parent)
    }
    return {
      kind: 'class',
      label: node.label,
      description: node.description,
      deprecated: node.deprecated ?? false,
      parent: node.parent,
      properties,
      constraints: (ontology.constraints ?? [])
        .filter((c) => c.node_type === node.label)
        .map((c) => `${c.type} (${c.property_name})`),
    }
  }
  if (selection?.kind === 'link') {
    const link = ontologyMap(ontology).links.find((l) => l.id === selection.id)
    if (!link) return null
    const relation = ontology.relationship_types.find((r) => r.label === link.relation)
    return {
      kind: 'link',
      id: link.id,
      source: link.source,
      relation: link.relation,
      target: link.target,
      description: relation?.description,
      deprecated: relation?.deprecated ?? false,
      properties: (relation?.properties ?? []).map((p) => detailProperty(p)),
    }
  }
  return null
}

/**
 * The classes and links the Concept search `query` matches, the same Concepts the tables
 * find: a class by its name, description or one of its attributes, and a link by its
 * relation's. Null for an empty search, which matches nothing in particular.
 */
export function searchMap(ontology: Ontology, query: string): MapFocus | null {
  if (query.trim() === '') return null
  const { classes, relations, attributes } = searchConcepts(conceptTables(ontology), query)
  const owners = new Set(attributes.map((a) => a.owner))
  const matchedRelations = new Set([...relations.map((r) => r.label), ...owners])
  return {
    classes: new Set(
      ontology.node_types.map((n) => n.label).filter((l) => owners.has(l) || classes.some((c) => c.label === l)),
    ),
    links: new Set(
      ontologyMap(ontology)
        .links.filter((l) => matchedRelations.has(l.relation))
        .map((l) => l.id),
    ),
  }
}

export interface Point {
  x: number
  y: number
}

/** Every node is drawn this size: nodes are uniform until Observed statistics size them. */
export const NODE_SIZE = { width: 160, height: 40 } as const

const elk = new ELK()

/**
 * Where each class goes: the top-left corner of its node, by class label. A stress
 * layout from a seeded force layout, so the same Map always lays out the same way. Each
 * pair of linked classes pulls together once, however many links run between them, and
 * a subclass link pulls like a Pattern link, so subclasses sit near their superclass.
 */
export async function layoutOntologyMap(map: OntologyMap): Promise<Record<string, Point>> {
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
  return Object.fromEntries((graph.children ?? []).map((n) => [n.id, { x: n.x ?? 0, y: n.y ?? 0 }]))
}
