/**
 * The change summary beside a comparison's Map: how many changes there are at each level,
 * and each changed Concept's changes in words.
 */
import { CLASSIFICATIONS, type Classification, type OntologyChange, type OwnerKind } from '@/api/ontology-diff'
import { codePointOrder } from '@/lib/compare'
import { attributeReference, CONCEPT_NOUN } from './concepts'
import {
  changesOfConcept,
  isDocumentationOnly,
  linkChanged,
  type OntologyComparison,
} from './ontology-map-comparison'
import { type MapSelection, relationSelection } from './ontology-map-focus'

/**
 * How much a change weighs in a comparison: documentation-only when only a description
 * differs, otherwise the Diff's classification. The core's Ontology Diff is the only
 * source of severity; documentation-only weighs less than any severity, without changing
 * the Diff's classification.
 */
export type ChangeLevel = 'documentation-only' | Classification

/** Every level, from the least to the most weighty. */
export const CHANGE_LEVELS: readonly ChangeLevel[] = ['documentation-only', ...CLASSIFICATIONS]

/** The level of one of a comparison's Diff changes. */
export const levelOf = (comparison: OntologyComparison, change: OntologyChange): ChangeLevel =>
  isDocumentationOnly(comparison, change) ? 'documentation-only' : change.classification

/** Orders levels from the least to the most weighty: a sort comparator. */
export const compareLevels = (a: ChangeLevel, b: ChangeLevel): number =>
  CHANGE_LEVELS.indexOf(a) - CHANGE_LEVELS.indexOf(b)

/** How many of the Diff's changes are at one level. */
export interface LevelCount {
  level: ChangeLevel
  count: number
}

/** One Diff change to a Concept, in words. */
export interface ChangeStatement {
  change: OntologyChange
  level: ChangeLevel
  /** The attribute it changed, or null for a change to the class or relation itself. */
  attribute: string | null
  /** What changed, e.g. "removed", "added, required", "class added", "description changed". */
  text: string
}

/** One class's or relation's changes. */
export interface ConceptChanges {
  kind: OwnerKind
  label: string
  /** Its weightiest change's level. */
  level: ChangeLevel
  /** The weightiest first, otherwise in the Diff's order. */
  statements: ChangeStatement[]
  /**
   * Where it is on the Map: a class itself, and a relation as its first changed Pattern
   * link (`relationSelection`: relations are not nodes). Null for a relation without Patterns.
   */
  selection: MapSelection | null
}

/** A comparison's changes, summarized. */
export interface ChangeSummary {
  /** The headline: a count per level, the weightiest first, leaving out levels with none. */
  counts: LevelCount[]
  /**
   * Every changed class and relation with changes beyond documentation, those changes
   * only, the weightiest first, equal ones by label.
   */
  concepts: ConceptChanges[]
  /** The documentation-only changes, set apart: grouped the same way, by label. */
  documentationOnly: ConceptChanges[]
}

/** How the Diff words them (`_KIND_NAMES` in ontology/diff.py). */
const DIFF_NOUN: Record<OwnerKind, string> = { node_type: 'node type', relationship_type: 'relationship type' }

/** `change`, to the class or relation `label` or to one of its attributes, in words. */
function statementOf(kind: OwnerKind, label: string, change: OntologyChange, level: ChangeLevel): ChangeStatement {
  if (change.concept_kind === 'property') {
    const { attribute } = attributeReference(change.concept)
    const text =
      change.kind === 'added'
        ? change.detail.startsWith('required ') ? 'added, required' : 'added'
        : change.kind === 'removed'
          ? 'removed'
          : change.detail
    return { change, level, attribute, text }
  }
  const text =
    change.kind === 'added' || change.kind === 'removed'
      ? `${CONCEPT_NOUN[kind]} ${change.kind}`
      : change.detail.replace(`${DIFF_NOUN[kind]} ${label} `, '')
  return { change, level, attribute: null, text }
}

/** The weightier first. */
const byWeight = <T extends { level: ChangeLevel }>(a: T, b: T) => compareLevels(b.level, a.level)

/** The summary of the comparison's Ontology Diff. */
export function summarizeChanges(comparison: OntologyComparison): ChangeSummary {
  const levels = comparison.diff.changes.map((c) => levelOf(comparison, c))
  const counts = [...CHANGE_LEVELS]
    .reverse()
    .map((level) => ({ level, count: levels.filter((l) => l === level).length }))
    .filter((c) => c.count > 0)
  const owners: [OwnerKind, string][] = [
    ...comparison.ontology.node_types.map((n): [OwnerKind, string] => ['node_type', n.label]),
    ...comparison.ontology.relationship_types.map((r): [OwnerKind, string] => ['relationship_type', r.label]),
  ]
  const grouped = owners.flatMap(([kind, label]): ConceptChanges[] => {
    const statements = changesOfConcept(comparison, kind, label)
      .map((c) => statementOf(kind, label, c, levelOf(comparison, c)))
      .sort(byWeight)
    const documented = statements.filter((s) => s.level === 'documentation-only')
    const selection = selectionOf(comparison, kind, label)
    return [statements.filter((s) => s.level !== 'documentation-only'), documented]
      .filter((s) => s.length > 0)
      .map((s) => ({ kind, label, level: s[0].level, statements: s, selection }))
  })
  const byLabel = (a: ConceptChanges, b: ConceptChanges) => codePointOrder(a.label, b.label) || codePointOrder(a.kind, b.kind)
  return {
    counts,
    concepts: grouped.filter((c) => c.level !== 'documentation-only').sort((a, b) => byWeight(a, b) || byLabel(a, b)),
    documentationOnly: grouped.filter((c) => c.level === 'documentation-only').sort(byLabel),
  }
}

/** Where the class or relation `label` is on the comparison's Map: a relation at its first changed link. */
const selectionOf = (comparison: OntologyComparison, kind: OwnerKind, label: string): MapSelection | null =>
  kind === 'node_type'
    ? { kind: 'class', label }
    : relationSelection(comparison.map.links, label, (l) => linkChanged(comparison, l))

/**
 * The summary's entry for what is selected on the Map: a class's own, or a link's
 * relation's, its documentation-only one when it has no other. Null when that has no
 * changes, or for any other selection.
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
        ? ['relationship_type', comparison.map.links.find((l) => l.id === selection.id)?.relation]
        : []
  const of = (c: ConceptChanges) => c.kind === kind && c.label === label
  return summary.concepts.find(of) ?? summary.documentationOnly.find(of) ?? null
}
