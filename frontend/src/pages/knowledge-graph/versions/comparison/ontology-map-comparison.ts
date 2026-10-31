/** Two Ontology Versions superimposed on one Map, each item marked with how it changed. */
import {
  CLASSIFICATIONS,
  type Classification,
  type OntologyChange,
  type OntologyDiff,
  type OwnerKind,
} from '@/api/ontology-diff'
import type { Ontology } from '@/api/ontology-versions'
import { codePointOrder } from '@/lib/compare'
import { patternId } from '../concepts'
import { ontologyMap, type OntologyMap, type PatternLink } from '../map/ontology-map'
import type { MapSelection } from '../map/ontology-map-focus'

/**
 * How an item of a comparison changed from the base to the target version: present in
 * one side only (added, removed), changed according to the Ontology Diff (modified),
 * changed only cosmetically (documentation-only: the Diff classes every change to it
 * cosmetic), or none of these. Not the Diff's own change kind, which is per Concept.
 */
export type MapChangeKind = 'added' | 'removed' | 'modified' | 'documentation-only' | 'unchanged'

/**
 * An item's change in a comparison, with the severity the Ontology Diff gives it, its
 * cosmetic changes left out (null when unchanged or documentation-only).
 */
export interface MapChange {
  kind: MapChangeKind
  severity: Classification | null
}

/**
 * How one attribute of a class changed, as the class lists it on a comparison's Map:
 * removed, added, or modified with the Diff's details of each change to it.
 */
export interface AttributeChange {
  name: string
  kind: Exclude<MapChangeKind, 'unchanged' | 'documentation-only'>
  /** The most severe of the Diff's changes to it. */
  severity: Classification
  /** A modified attribute's changes, as the Diff words them; empty when added or removed. */
  details: string[]
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
  /** The two Ontologies compared, from `base` to `target`. */
  base: Ontology
  target: Ontology
  /** The core's Ontology Diff from the base to the target, behind every severity. */
  diff: OntologyDiff
  /**
   * Each item's change, by class label, Pattern link id and subclass link id, and each
   * class's changed attributes by class label (empty when none changed).
   */
  changes: {
    classes: Record<string, MapChange>
    links: Record<string, MapChange>
    subclassLinks: Record<string, MapChange>
    attributes: Record<string, AttributeChange[]>
  }
}

/** The most severe of `classifications`, or null for none. */
const mostSevere = (classifications: Classification[]): Classification | null =>
  classifications.reduce<Classification | null>(
    (a, c) => (a === null || CLASSIFICATIONS.indexOf(c) > CLASSIFICATIONS.indexOf(a) ? c : a),
    null,
  )

/** A comparison's Ontology Diff. */
type ComparedOntologies = Pick<OntologyComparison, 'diff'>

/**
 * The Diff's changes to one class or relation: those to the Concept itself and to its
 * attributes, which the Diff records apart from their owner (an attribute change states
 * its owner and the owner's kind, so a class and a relation sharing a label stay apart).
 */
export function changesOfConcept({ diff }: ComparedOntologies, kind: OwnerKind, label: string): OntologyChange[] {
  return diff.changes.filter((c) =>
    c.concept_kind === 'property'
      ? c.owner_kind === kind && c.owner === label
      : c.concept_kind === kind && c.concept === label,
  )
}

/**
 * The Diff's changes to one Pattern link. The Diff records them against its relation:
 * an endpoint change belongs to the one link whose Pattern it states, any other change
 * to every link of the relation.
 */
function changesOfLink(compared: ComparedOntologies, link: PatternLink): OntologyChange[] {
  return changesOfConcept(compared, 'relationship_type', link.relation).filter(
    (c) => c.pattern === undefined || patternId(c.pattern) === link.id,
  )
}

/**
 * An item's change from which sides have it and the Diff's changes to it: added or
 * removed by side; otherwise modified in the severity of its changes that are not
 * cosmetic, documentation-only when cosmetic ones are all it has, or unchanged.
 */
function mapChange(inBase: boolean, inTarget: boolean, changes: OntologyChange[]): MapChange {
  const severity = mostSevere(structural(changes).map((c) => c.classification))
  const kind: MapChangeKind = !inBase
    ? 'added'
    : !inTarget
      ? 'removed'
      : severity
        ? 'modified'
        : changes.length > 0
          ? 'documentation-only'
          : 'unchanged'
  return { kind, severity }
}

/** The changes of `changes` that are not cosmetic. */
const structural = (changes: OntologyChange[]) => changes.filter((c) => c.classification !== 'cosmetic')

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
  const compared = { base, target, diff }
  const classChange = (label: string, inBase: boolean, inTarget: boolean) =>
    mapChange(inBase, inTarget, changesOfConcept(compared, 'node_type', label))

  const classes = Object.fromEntries(
    map.nodes.map((n): [string, MapChange] => [
      n.label,
      classChange(n.label, baseClasses.has(n.label), targetClasses.has(n.label)),
    ]),
  )
  // A link takes the severity of its own endpoint change and of its relation's other changes.
  const links = Object.fromEntries(
    map.links.map((l): [string, MapChange] => [
      l.id,
      mapChange(baseLinks.has(l.id), targetLinks.has(l.id), changesOfLink(compared, l)),
    ]),
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
      const [inBase, inTarget] = [baseSubclassLinks.has(l.id), targetSubclassLinks.has(l.id)]
      if (inBase && inTarget) return [l.id, { kind: 'unchanged', severity: null }]
      return [l.id, { kind: inBase ? 'removed' : 'added', severity: classChange(l.child, true, true).severity }]
    }),
  )
  // Only the attributes with more than cosmetic changes are listed.
  const attributes = Object.fromEntries(
    map.nodes.map((n) => [n.label, attributeChanges(structural(changesOfConcept(compared, 'node_type', n.label)))]),
  )
  return {
    map: { ...map, subclassLinks },
    ontology,
    base,
    target,
    diff,
    changes: { classes, links, subclassLinks: subclassLinkChanges, attributes },
  }
}

/**
 * The changed attributes among one class's Diff changes, one entry per attribute, by
 * name in code-point order, as the Diff sorts them.
 */
function attributeChanges(changes: OntologyChange[]): AttributeChange[] {
  const byName = new Map<string, OntologyChange[]>()
  for (const c of changes) {
    if (c.attribute === undefined) continue
    byName.set(c.attribute, [...(byName.get(c.attribute) ?? []), c])
  }
  return [...byName]
    .sort(([a], [b]) => codePointOrder(a, b))
    .map(([name, cs]) => {
      // Added or removed is one change; any other is a modification, one change per detail.
      const kind = cs.length === 1 && (cs[0].kind === 'added' || cs[0].kind === 'removed') ? cs[0].kind : 'modified'
      return {
        name,
        kind,
        severity: mostSevere(cs.map((c) => c.classification))!,
        details: kind === 'modified' ? cs.map((c) => c.detail) : [],
      }
    })
}

/**
 * The Diff's changes behind a selection on a comparison's Map: a class's own (its
 * attributes' included), or a link's relation's. Empty when nothing changed or nothing
 * is selected.
 */
export function changesOf(comparison: OntologyComparison, selection: MapSelection | null): OntologyChange[] {
  if (selection?.kind === 'class') return changesOfConcept(comparison, 'node_type', selection.label)
  if (selection?.kind === 'link') {
    const link = comparison.map.links.find((l) => l.id === selection.id)
    return link ? changesOfLink(comparison, link) : []
  }
  return []
}

/** Whether a comparison's link changed in any way, documentation-only included. */
export const linkChanged = (comparison: OntologyComparison, link: PatternLink) =>
  comparison.changes.links[link.id]?.kind !== 'unchanged'

/** The items of `items` that `besides` has none of, by `key`. */
function onlyIn<T>(items: T[], besides: T[], key: (item: T) => string): T[] {
  const keys = new Set(besides.map(key))
  return items.filter((i) => !keys.has(key(i)))
}
