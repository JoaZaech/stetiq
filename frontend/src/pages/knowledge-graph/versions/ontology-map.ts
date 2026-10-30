/**
 * The Ontology Map: an Ontology as a node-link dataset (docs/ontology-view-abstraction.md).
 * Classes are nodes, keyed by label. Each Pattern is a link, keyed by
 * (source, relation, target); relations are not nodes. Each superclass is a subclass
 * link, a separate link type keyed by (child, parent). No React and no I/O here.
 */
import ELK from 'elkjs/lib/elk.bundled.js'
import type { Classification, OntologyChange, OntologyDiff } from '@/api/ontology-diff'
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

/**
 * How an item of a comparison changed from the base to the target version: present in
 * one side only (added, removed), changed according to the Ontology Diff (modified), or
 * neither. Not the Diff's own change kind, which is per Concept.
 */
export type MapChangeKind = 'added' | 'removed' | 'modified' | 'unchanged'

/** An item's change in a comparison, with the severity the Ontology Diff gives it (null when unchanged). */
export interface MapChange {
  kind: MapChangeKind
  severity: Classification | null
}

/** Two Ontology Versions superimposed: the union network of both, and how each item changed. */
export interface OntologyComparison {
  /** Every class and link of either side, laid out as one Map. */
  map: OntologyMap
  /**
   * Both Ontologies as one: the target's Concepts, Patterns and constraints, then those
   * only the base has. What to detail or search for any item of `map`.
   */
  ontology: Ontology
  /** The core's Ontology Diff from the base to the target, behind every severity. */
  diff: OntologyDiff
  /** Each item's change, by class label, Pattern link id and subclass link id. */
  changes: {
    classes: Record<string, MapChange>
    links: Record<string, MapChange>
    subclassLinks: Record<string, MapChange>
  }
}

const SEVERITIES: readonly Classification[] = ['additive', 'deprecating', 'breaking']

/** The most severe of `classifications`, or null for none. */
const mostSevere = (classifications: Classification[]): Classification | null =>
  classifications.reduce<Classification | null>(
    (a, c) => (a === null || SEVERITIES.indexOf(c) > SEVERITIES.indexOf(a) ? c : a),
    null,
  )

/**
 * The Diff's changes to one class or relation: those to the Concept itself and to its
 * attributes (`<owner>.<attribute>`), which the Diff records apart from their owner.
 */
export function changesOfConcept(
  diff: OntologyDiff,
  kind: 'node_type' | 'relationship_type',
  label: string,
): OntologyChange[] {
  return diff.changes.filter((c) =>
    c.concept_kind === 'property'
      ? c.concept.slice(0, c.concept.lastIndexOf('.')) === label
      : c.concept_kind === kind && c.concept === label,
  )
}

/** The Pattern an endpoint change names, as its link id (`Pattern.__str__`); null for any other change. */
const endpointPattern = (change: OntologyChange) =>
  /^endpoint pattern (.*) (?:added|removed)$/.exec(change.detail)?.[1] ?? null

/**
 * The Diff's changes to one Pattern link. The Diff records them against its relation:
 * an endpoint change belongs to the one link it names, any other change to every link
 * of the relation.
 */
function changesOfLink(diff: OntologyDiff, link: PatternLink): OntologyChange[] {
  return changesOfConcept(diff, 'relationship_type', link.relation).filter((c) => {
    const pattern = endpointPattern(c)
    return pattern === null || pattern === link.id
  })
}

/** Added or removed by which side has the item; otherwise modified when the Diff gives it a severity. */
const changeKind = (inBase: boolean, inTarget: boolean, severity: Classification | null): MapChangeKind =>
  !inBase ? 'added' : !inTarget ? 'removed' : severity ? 'modified' : 'unchanged'

/**
 * The comparison from `base` to `target`. Whether an item is added or removed comes from
 * the two Ontologies; its severity only from `diff`, the core's Ontology Diff between them.
 */
export function compareOntologies(base: Ontology, target: Ontology, diff: OntologyDiff): OntologyComparison {
  const baseMap = ontologyMap(base)
  const targetMap = ontologyMap(target)
  const ontology: Ontology = {
    node_types: [...target.node_types, ...onlyIn(base.node_types, target.node_types, (n) => n.label)],
    relationship_types: [
      ...target.relationship_types,
      ...onlyIn(base.relationship_types, target.relationship_types, (r) => r.label),
    ],
    patterns: [...target.patterns, ...onlyIn(base.patterns, target.patterns, (p) => JSON.stringify(p))],
    constraints: [
      ...(target.constraints ?? []),
      ...onlyIn(base.constraints ?? [], target.constraints ?? [], (c) => JSON.stringify(c)),
    ],
  }
  // Routes are over the union, so a removed link bends apart from the links beside it.
  const map = ontologyMap(ontology)

  const [baseClasses, targetClasses] = [baseMap, targetMap].map((m) => new Set(m.nodes.map((n) => n.label)))
  const [baseLinks, targetLinks] = [baseMap, targetMap].map((m) => new Set(m.links.map((l) => l.id)))
  const severity = (kind: 'node_type' | 'relationship_type', label: string) =>
    mostSevere(changesOfConcept(diff, kind, label).map((c) => c.classification))

  const classes = Object.fromEntries(
    map.nodes.map((n): [string, MapChange] => {
      const s = severity('node_type', n.label)
      return [n.label, { kind: changeKind(baseClasses.has(n.label), targetClasses.has(n.label), s), severity: s }]
    }),
  )
  // A link takes the severity of its own endpoint change and of its relation's other changes.
  const links = Object.fromEntries(
    map.links.map((l): [string, MapChange] => {
      const s = mostSevere(changesOfLink(diff, l).map((c) => c.classification))
      return [l.id, { kind: changeKind(baseLinks.has(l.id), targetLinks.has(l.id), s), severity: s }]
    }),
  )
  // A class has one superclass per side, so a moved class has both its old and new link.
  const subclassLinks = [
    ...targetMap.subclassLinks,
    ...onlyIn(baseMap.subclassLinks, targetMap.subclassLinks, (l) => l.id),
  ]
  const [baseSubclassLinks, targetSubclassLinks] = [baseMap, targetMap].map(
    (m) => new Set(m.subclassLinks.map((l) => l.id)),
  )
  // A subclass link is never modified; added or removed, it takes its subclass's severity.
  const subclassLinkChanges = Object.fromEntries(
    subclassLinks.map((l): [string, MapChange] => {
      const kind = changeKind(baseSubclassLinks.has(l.id), targetSubclassLinks.has(l.id), null)
      return [l.id, { kind, severity: kind === 'unchanged' ? null : severity('node_type', l.child) }]
    }),
  )
  return {
    map: { ...map, subclassLinks },
    ontology,
    diff,
    changes: { classes, links, subclassLinks: subclassLinkChanges },
  }
}

/**
 * The Diff's changes behind a selection on a comparison's Map: a class's own (its
 * attributes' included), or a link's relation's. Empty when nothing changed or nothing
 * is selected.
 */
export function changesOf(
  { map, diff }: OntologyComparison,
  selection: MapSelection | null,
): OntologyChange[] {
  if (selection?.kind === 'class') return changesOfConcept(diff, 'node_type', selection.label)
  if (selection?.kind === 'link') {
    const link = map.links.find((l) => l.id === selection.id)
    return link ? changesOfLink(diff, link) : []
  }
  return []
}

/** The items of `items` that `besides` has none of, by `key`. */
function onlyIn<T>(items: T[], besides: T[], key: (item: T) => string): T[] {
  const keys = new Set(besides.map(key))
  return items.filter((i) => !keys.has(key(i)))
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

/**
 * What is selected on the Map: one class, by label, one Pattern link, by id, or two
 * classes, to find the shortest paths between them.
 */
export type MapSelection =
  | { kind: 'class'; label: string }
  | { kind: 'link'; id: string }
  | { kind: 'path'; from: string; to: string }

/** The classes and links a selection keeps in focus; the rest of the Map fades. */
export interface MapFocus {
  classes: Set<string>
  links: Set<string>
}

/**
 * What stays in focus for a selection: a class with its neighbours and the links to them,
 * a link with the two classes it joins, or two classes with every shortest path between
 * them (just the two when there is none). Null when nothing (that still exists) is
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
  if (selection?.kind === 'path') {
    const { from, to } = selection
    if (!map.nodes.some((n) => n.label === from) || !map.nodes.some((n) => n.label === to)) return null
    const paths = shortestPaths(map, from, to)
    const steps = paths.flatMap((p) => p.steps)
    return {
      classes: new Set([from, to, ...paths.flatMap((p) => p.classes), ...steps.flatMap((s) => s.ancestors)]),
      links: new Set(steps.flatMap((s) => s.links)),
    }
  }
  return null
}

/** One step of a path: from one class to the next. */
export interface PathStep {
  /** Link ids of every Pattern link that joins the two classes, sorted: the step can take any of them. */
  links: string[]
  /**
   * The superclasses, sorted, that the step climbs from either of its classes to reach an
   * inherited Pattern's class; empty when every link is the classes' own.
   */
  ancestors: string[]
}

/** A path between two classes: the classes it passes, in order, and the steps between them. */
export interface MapPath {
  classes: string[]
  steps: PathStep[]
}

/**
 * Every shortest path from class `from` to class `to`, over Pattern links taken either way
 * round. A class also takes part in each Pattern of its superclasses, at that superclass's
 * end: inherited Patterns are derived here, along the Map's subclass links, and never become
 * links of their own. Empty when no path exists, or either class is not on the Map.
 */
export function shortestPaths(map: OntologyMap, from: string, to: string): MapPath[] {
  const labels = new Set(map.nodes.map((n) => n.label))
  if (!labels.has(from) || !labels.has(to)) return []
  const parents = new Map(map.subclassLinks.map((l) => [l.child, l.parent]))
  // A class, then its superclasses, nearest first; a cycle ends the chain.
  const chain = (c: string) => {
    const classes = [c]
    let parent = parents.get(c)
    while (parent !== undefined && !classes.includes(parent)) {
      classes.push(parent)
      parent = parents.get(parent)
    }
    return classes
  }
  const chains = new Map([...labels].map((c) => [c, chain(c)]))
  const stepBetween = (a: string, b: string): PathStep => {
    const [up, down] = [chains.get(a)!, chains.get(b)!]
    const links: string[] = []
    const ancestors = new Set<string>()
    for (const l of map.links) {
      for (const [x, y] of [[up, down], [down, up]]) {
        const [i, j] = [x.indexOf(l.source), y.indexOf(l.target)]
        if (i === -1 || j === -1) continue
        if (!links.includes(l.id)) links.push(l.id)
        for (const c of [...x.slice(1, i + 1), ...y.slice(1, j + 1)]) ancestors.add(c)
      }
    }
    return { links: links.sort(), ancestors: [...ancestors].sort() }
  }

  // Breadth first from `from`, keeping every previous class at the shortest distance.
  const previous = new Map<string, string[]>([[from, []]])
  let frontier = [from]
  while (frontier.length > 0 && !previous.has(to)) {
    const next = new Map<string, string[]>()
    for (const a of frontier) {
      for (const b of [...labels].sort()) {
        if (previous.has(b) || stepBetween(a, b).links.length === 0) continue
        next.set(b, [...(next.get(b) ?? []), a])
      }
    }
    for (const [b, before] of next) previous.set(b, before)
    frontier = [...next.keys()]
  }
  if (!previous.has(to)) return []

  // Every path back from `to`, then each reversed to run from `from`.
  const back = (c: string): string[][] =>
    c === from ? [[from]] : previous.get(c)!.flatMap((p) => back(p).map((path) => [...path, c]))
  return back(to).map((classes) => ({
    classes,
    steps: classes.slice(1).map((b, i) => stepBetween(classes[i], b)),
  }))
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
