/**
 * What the Map brings forward: a selection's focus and details, and the Concept search's
 * matches.
 */
import type { Ontology, OntologyProperty } from '@/api/ontology-versions'
import type { OntologyComparison } from '../comparison/ontology-map-comparison'
import { type ClassOrRelation, constraintsOf, superclassChain } from '../concepts'
import { ontologyMap, type OntologyMap, type PatternLink } from './ontology-map'
import { type MapPath, shortestPaths } from './ontology-map-paths'
import type { SearchResults } from './ontology-map-search'

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

/**
 * Where relation `label` is on the Map, which draws a relation as its Pattern links: the
 * first of its `links` that `prefer` picks, else its first. Null when `links` has none of
 * its links.
 */
export function relationSelection(
  links: readonly PatternLink[],
  label: string,
  prefer: (link: PatternLink) => boolean,
): MapSelection | null {
  const own = links.filter((l) => l.relation === label)
  const link = own.find(prefer) ?? own[0]
  return link ? { kind: 'link', id: link.id } : null
}

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
    const paths = pathsBetween(map, selection)
    return paths && pathFocus(selection, paths)
  }
  return null
}

/**
 * The classes and Pattern links a comparison changed, documentation-only ones included:
 * every item not unchanged.
 */
export function changedOf({ changes }: Pick<OntologyComparison, 'changes'>): MapFocus {
  const changed = (items: Record<string, { kind: string }>) =>
    new Set(Object.keys(items).filter((key) => items[key].kind !== 'unchanged'))
  return { classes: changed(changes.classes), links: changed(changes.links) }
}

/**
 * What stays readable as context outside `focus`: the `changed` items it leaves out, so a
 * selection never hides what a comparison changed. Only the rest fades fully.
 */
export function contextOf(focus: MapFocus, changed: MapFocus): MapFocus {
  const outside = (items: Set<string>, focused: Set<string>) => new Set([...items].filter((key) => !focused.has(key)))
  return { classes: outside(changed.classes, focus.classes), links: outside(changed.links, focus.links) }
}

/**
 * The shortest paths in `map` between a path selection's two classes (none when nothing
 * joins them); null when `map` lacks either class.
 */
export function pathsBetween(map: OntologyMap, { from, to }: { from: string; to: string }): MapPath[] | null {
  if (!map.nodes.some((n) => n.label === from) || !map.nodes.some((n) => n.label === to)) return null
  return shortestPaths(map, from, to)
}

/**
 * What stays in focus for the shortest `paths` between two classes, as `shortestPaths`
 * finds them: the two classes, every class and link along a path, and the superclasses a
 * step climbs to reach an inherited Pattern.
 */
export function pathFocus({ from, to }: { from: string; to: string }, paths: readonly MapPath[]): MapFocus {
  const steps = paths.flatMap((p) => p.steps)
  return {
    classes: new Set([from, to, ...paths.flatMap((p) => p.classes), ...steps.flatMap((s) => s.ancestors)]),
    links: new Set(steps.flatMap((s) => s.links)),
  }
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
 * is selected. A class's inherited properties come from its `superclassChain`.
 */
export function detailsOf(ontology: Ontology, selection: MapSelection | null): MapDetails | null {
  if (selection?.kind === 'class') {
    const [node, ...ancestors] = superclassChain(ontology, selection.label)
    if (!node) return null
    const properties: DetailProperty[] = []
    for (const c of [node, ...ancestors]) {
      for (const p of c.properties ?? []) {
        if (properties.some((q) => q.name === p.name)) continue
        properties.push(detailProperty(p, c === node ? undefined : c.label))
      }
    }
    return {
      kind: 'class',
      label: node.label,
      description: node.description,
      deprecated: node.deprecated ?? false,
      parent: node.parent,
      properties,
      constraints: constraintsOf(ontology, node.label),
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
 * The classes and links of `map` that the Concept search `query` names, read from its
 * `results` (`searchOntology`): a class by its name, and a link by its relation's.
 * Concepts it only mentions are listed, not highlighted. Null for an empty search, which
 * matches nothing in particular.
 */
export function searchMap(map: OntologyMap, query: string, { names }: SearchResults): MapFocus | null {
  if (query.trim() === '') return null
  const named = (kind: ClassOrRelation['kind']) => new Set(names.filter((r) => r.kind === kind).map((r) => r.label))
  const relations = named('relation')
  return {
    classes: named('class'),
    links: new Set(map.links.filter((l) => relations.has(l.relation)).map((l) => l.id)),
  }
}
