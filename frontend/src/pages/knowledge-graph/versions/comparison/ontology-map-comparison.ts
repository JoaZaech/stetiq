/**
 * The comparison of two Ontology Versions: everything the Map, its change summary and the
 * comparison Table read from (base, target, Ontology Diff). The two versions superimposed
 * on one Map, each item marked with how it changed; the change summary, a count per level
 * and each changed Concept's changes in words, by level; and where a Concept is on the Map.
 */
import {
  type Classification,
  compareSeverity,
  isCosmetic,
  MOST_SEVERE_FIRST,
  mostSevere,
  type OntologyChange,
  type OntologyDiff,
  type OwnerKind,
} from '@/api/ontology-diff'
import type { Ontology } from '@/api/ontology-versions'
import { codePointOrder } from '@/lib/compare'
import { type ClassOrRelation, CONCEPT_NOUN, patternId, relationOfPattern } from '../concepts'
import { ontologyMap, type OntologyMap, type PatternLink } from '../map/ontology-map'
import { type MapSelection, relationSelection } from '../map/ontology-map-focus'

/**
 * How an item of a comparison changed from the base to the target version: present in
 * one side only (added, removed), changed according to the Ontology Diff (modified),
 * changed only cosmetically (cosmetic: the Diff classes every change to it cosmetic; the
 * UI calls it documentation-only), or none of these. Not the Diff's own change kind,
 * which is per Concept.
 */
export type MapChangeKind = 'added' | 'removed' | 'modified' | 'cosmetic' | 'unchanged'

/**
 * An item's change in a comparison, with the severity the Ontology Diff gives it, its
 * cosmetic changes left out (null when unchanged or cosmetic).
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
  kind: Exclude<MapChangeKind, 'unchanged' | 'cosmetic'>
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

/** A comparison's Ontology Diff. */
type ComparedOntologies = Pick<OntologyComparison, 'diff'>

/**
 * The Diff's changes to one class or relation: those to the Concept itself and to its
 * attributes, which the Diff records apart from their owner (an attribute change states
 * its owner and the owner's kind, so a class and a relation sharing a label stay apart).
 */
function changesOfConcept({ diff }: ComparedOntologies, kind: OwnerKind, label: string): OntologyChange[] {
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
function changesOfLink(compared: ComparedOntologies, link: Pick<PatternLink, 'id' | 'relation'>): OntologyChange[] {
  return changesOfConcept(compared, 'relationship_type', link.relation).filter(
    (c) => c.concept_kind !== 'relationship_type' || c.pattern === undefined || patternId(c.pattern) === link.id,
  )
}

/**
 * An item's change from which sides have it and the Diff's changes to it: added or
 * removed by side; otherwise modified in the severity of its changes that are not
 * cosmetic, cosmetic when only cosmetic ones are left, or unchanged.
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
          ? 'cosmetic'
          : 'unchanged'
  return { kind, severity }
}

/** Whether `change` is cosmetic: its Diff classification decides it (`isCosmetic`). */
const cosmetic = (change: OntologyChange) => isCosmetic(change.classification)

/** The changes of `changes` that are not cosmetic. */
const structural = (changes: OntologyChange[]) => changes.filter((c) => !cosmetic(c))

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
    if (c.concept_kind !== 'property') continue
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
    const relation = relationOfPattern(comparison.ontology, selection.id)
    return relation === undefined ? [] : changesOfLink(comparison, { id: selection.id, relation })
  }
  return []
}

/** Whether a comparison's link changed in any way, cosmetically included. */
const linkChanged = (comparison: OntologyComparison, link: PatternLink) =>
  comparison.changes.links[link.id]?.kind !== 'unchanged'

/**
 * What selecting a class or relation selects on a comparison's Map, given the Pattern
 * links `shown`: a class itself, and a relation (relations are not nodes) its first shown
 * changed link, else its first shown link; null when none of its links is shown. The
 * change summary and the Map both select through this, so they agree whatever a filter hides.
 */
export function selectionOf(
  comparison: OntologyComparison,
  concept: ClassOrRelation,
  shown: readonly PatternLink[],
): MapSelection | null {
  return concept.kind === 'class'
    ? { kind: 'class', label: concept.label }
    : relationSelection(shown, concept.label, (l) => linkChanged(comparison, l))
}

/** How many of the Diff's changes are at one level (a change's level is its classification). */
export interface LevelCount {
  level: Classification
  count: number
}

/** One Diff change to a Concept, in words. */
export interface ChangeStatement {
  change: OntologyChange
  /** Its level when it differs from its section's, else null: the section says it once. */
  level: Classification | null
  /** The attribute it changed, or null for a change to the class or relation itself. */
  attribute: string | null
  /** What changed, e.g. "removed", "added, required", "class added", "description changed". */
  text: string
}

/** One class's or relation's changes, as the change summary lists them. */
export interface ConceptChanges {
  kind: OwnerKind
  label: string
  /** The most severe first, otherwise in the Diff's order. */
  statements: ChangeStatement[]
}

/** The changed Concepts whose most severe change is at `level`, by label. */
export interface SummarySection {
  level: Classification
  concepts: ConceptChanges[]
}

/** A comparison's changes, summarized. */
export interface ChangeSummary {
  /** The headline: a count per level, the most severe first, leaving out levels with none. */
  counts: LevelCount[]
  /** Every changed class and relation, partitioned by level, the most severe first, leaving out levels with none. */
  sections: SummarySection[]
}

/**
 * `change`, to the class or relation of `kind` or to one of its attributes, in words, in
 * the section of `section`. A change to a Concept that is still there is its Diff detail,
 * which never repeats the Concept.
 */
function statementOf(kind: OwnerKind, change: OntologyChange, section: Classification): ChangeStatement {
  const level = change.classification === section ? null : change.classification
  if (change.concept_kind === 'property') {
    const text =
      change.kind === 'added'
        ? change.required ? 'added, required' : 'added'
        : change.kind === 'removed'
          ? 'removed'
          : change.detail
    return { change, level, attribute: change.attribute, text }
  }
  const text = change.kind === 'added' || change.kind === 'removed' ? `${CONCEPT_NOUN[kind]} ${change.kind}` : change.detail
  return { change, level, attribute: null, text }
}

/** The change summary of the comparison's Ontology Diff. */
export function summarizeChanges(comparison: OntologyComparison): ChangeSummary {
  const levels = comparison.diff.changes.map((c) => c.classification)
  const counts = MOST_SEVERE_FIRST.map((level) => ({ level, count: levels.filter((l) => l === level).length })).filter(
    (c) => c.count > 0,
  )
  const owners: [OwnerKind, string][] = [
    ...comparison.ontology.node_types.map((n): [OwnerKind, string] => ['node_type', n.label]),
    ...comparison.ontology.relationship_types.map((r): [OwnerKind, string] => ['relationship_type', r.label]),
  ]
  // Each changed Concept, in the section of its most severe change.
  const entries = owners.flatMap(([kind, label]) => {
    const changes = changesOfConcept(comparison, kind, label)
    const level = mostSevere(changes.map((c) => c.classification))
    if (level === null) return []
    const statements = changes
      .toSorted((a, b) => compareSeverity(b.classification, a.classification))
      .map((c) => statementOf(kind, c, level))
    return [{ level, concept: { kind, label, statements } }]
  })
  const byLabel = (a: ConceptChanges, b: ConceptChanges) => codePointOrder(a.label, b.label) || codePointOrder(a.kind, b.kind)
  const sections = MOST_SEVERE_FIRST.map((level) => ({
    level,
    concepts: entries.filter((e) => e.level === level).map((e) => e.concept).sort(byLabel),
  })).filter((s) => s.concepts.length > 0)
  return { counts, sections }
}

/**
 * The summary's entry for what is selected on the Map: a class's own, or a link's
 * relation's. Null when that has no changes, or for any other selection.
 */
export function summaryConceptOf(
  comparison: OntologyComparison,
  summary: ChangeSummary,
  selection: MapSelection | null,
): ConceptChanges | null {
  const [kind, label] =
    selection?.kind === 'class'
      ? ['node_type', selection.label]
      : selection?.kind === 'link'
        ? ['relationship_type', relationOfPattern(comparison.ontology, selection.id)]
        : []
  const of = (c: ConceptChanges) => c.kind === kind && c.label === label
  return summary.sections.flatMap((s) => s.concepts).find(of) ?? null
}

/** The items of `items` that `besides` has none of, by `key`. */
function onlyIn<T>(items: T[], besides: T[], key: (item: T) => string): T[] {
  const keys = new Set(besides.map(key))
  return items.filter((i) => !keys.has(key(i)))
}
