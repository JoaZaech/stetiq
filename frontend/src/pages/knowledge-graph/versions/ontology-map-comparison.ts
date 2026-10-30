/** Two Ontology Versions superimposed on one Map, each item marked with how it changed. */
import { CLASSIFICATIONS, type Classification, type OntologyChange, type OntologyDiff } from '@/api/ontology-diff'
import type { Ontology } from '@/api/ontology-versions'
import { ontologyMap, type OntologyMap, type PatternLink } from './ontology-map'
import type { MapSelection } from './ontology-map-focus'

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
  /** The two Ontologies compared, from `base` to `target`. */
  base: Ontology
  target: Ontology
  /** The core's Ontology Diff from the base to the target, behind every severity. */
  diff: OntologyDiff
  /** Each item's change, by class label, Pattern link id and subclass link id. */
  changes: {
    classes: Record<string, MapChange>
    links: Record<string, MapChange>
    subclassLinks: Record<string, MapChange>
  }
}

/** The most severe of `classifications`, or null for none. */
const mostSevere = (classifications: Classification[]): Classification | null =>
  classifications.reduce<Classification | null>(
    (a, c) => (a === null || CLASSIFICATIONS.indexOf(c) > CLASSIFICATIONS.indexOf(a) ? c : a),
    null,
  )

/** A comparison's two Ontologies and the Diff between them. */
type ComparedOntologies = Pick<OntologyComparison, 'base' | 'target' | 'diff'>

/** A class's or a relation's Concept kind: the Concepts that own attributes. */
type OwnerKind = Exclude<OntologyChange['concept_kind'], 'property'>

/**
 * The Diff's changes to one class or relation: those to the Concept itself and to its
 * attributes (`<owner>.<attribute>`), which the Diff records apart from their owner.
 */
export function changesOfConcept(
  { base, target, diff }: ComparedOntologies,
  kind: OwnerKind,
  label: string,
): OntologyChange[] {
  return diff.changes.filter((c) =>
    c.concept_kind === 'property'
      ? c.concept.startsWith(`${label}.`) &&
        attributeChanged(base, target, kind, label, c.concept.slice(label.length + 1))
      : c.concept_kind === kind && c.concept === label,
  )
}

/**
 * Whether the class or relation `label` declares attribute `name` differently in `base`
 * and `target`, a class's constraints on it included. The Diff names a class's and a
 * relation's attributes alike, so this tells which of two Concepts sharing a label owns
 * an attribute change.
 */
function attributeChanged(
  base: Ontology,
  target: Ontology,
  kind: OwnerKind,
  label: string,
  name: string,
): boolean {
  const declaration = (ontology: Ontology) => {
    const concepts = kind === 'node_type' ? ontology.node_types : ontology.relationship_types
    const attribute = concepts.find((c) => c.label === label)?.properties?.find((p) => p.name === name)
    const constraints =
      kind === 'node_type'
        ? (ontology.constraints ?? []).filter((c) => c.node_type === label && c.property_name === name)
        : []
    return JSON.stringify([attribute ?? null, constraints])
  }
  return declaration(base) !== declaration(target)
}

/**
 * The Pattern an endpoint change names, as its link id (`Pattern.__str__`); null for any
 * other change. The wording is `_diff_patterns`' in `ontology/diff.py`, which the Diff
 * carries only as text; e2e/ontology-map-changes.spec.ts fails if it changes.
 */
const endpointPattern = (change: OntologyChange) =>
  /^endpoint pattern (.*) (?:added|removed)$/.exec(change.detail)?.[1] ?? null

/**
 * The Diff's changes to one Pattern link. The Diff records them against its relation:
 * an endpoint change belongs to the one link it names, any other change to every link
 * of the relation.
 */
function changesOfLink(compared: ComparedOntologies, link: PatternLink): OntologyChange[] {
  return changesOfConcept(compared, 'relationship_type', link.relation).filter((c) => {
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
  const severity = (kind: OwnerKind, label: string) =>
    mostSevere(changesOfConcept({ base, target, diff }, kind, label).map((c) => c.classification))

  const classes = Object.fromEntries(
    map.nodes.map((n): [string, MapChange] => {
      const s = severity('node_type', n.label)
      return [n.label, { kind: changeKind(baseClasses.has(n.label), targetClasses.has(n.label), s), severity: s }]
    }),
  )
  // A link takes the severity of its own endpoint change and of its relation's other changes.
  const links = Object.fromEntries(
    map.links.map((l): [string, MapChange] => {
      const s = mostSevere(changesOfLink({ base, target, diff }, l).map((c) => c.classification))
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
    base,
    target,
    diff,
    changes: { classes, links, subclassLinks: subclassLinkChanges },
  }
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

/** The items of `items` that `besides` has none of, by `key`. */
function onlyIn<T>(items: T[], besides: T[], key: (item: T) => string): T[] {
  const keys = new Set(besides.map(key))
  return items.filter((i) => !keys.has(key(i)))
}
