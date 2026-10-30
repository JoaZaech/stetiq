/**
 * The change summary beside a comparison's Map: how many changes there are at each level,
 * and each changed Concept's changes in words.
 */
import { CLASSIFICATIONS, type Classification, type OntologyChange } from '@/api/ontology-diff'
import { changesOfConcept, type OntologyComparison, type OwnerKind } from './ontology-map-comparison'

/**
 * How much a change weighs in the summary. For now the Diff's classification; the core's
 * Ontology Diff is the only source of severity.
 */
export type ChangeLevel = Classification

/** Every level, from the least to the most weighty. */
export const CHANGE_LEVELS: readonly ChangeLevel[] = CLASSIFICATIONS

/** The level of one of a comparison's Diff changes. */
const levelOf = (change: OntologyChange): ChangeLevel => change.classification

/** How weighty `level` is: the higher, the weightier. */
const weight = (level: ChangeLevel) => CHANGE_LEVELS.indexOf(level)

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
}

/** A comparison's changes, summarized. */
export interface ChangeSummary {
  /** The headline: a count per level, the weightiest first, leaving out levels with none. */
  counts: LevelCount[]
  /** Every changed class and relation, the weightiest first, equal ones by label. */
  concepts: ConceptChanges[]
}

/** The words for a class and a relation, as the Map says them. */
const CONCEPT_NOUN: Record<OwnerKind, string> = { node_type: 'class', relationship_type: 'relation' }
/** How the Diff words them (`_KIND_NAMES` in ontology/diff.py). */
const DIFF_NOUN: Record<OwnerKind, string> = { node_type: 'node type', relationship_type: 'relationship type' }

/** `change`, to the class or relation `label` or to one of its attributes, in words. */
function statementOf(kind: OwnerKind, label: string, change: OntologyChange): ChangeStatement {
  const level = levelOf(change)
  if (change.concept_kind === 'property') {
    const attribute = change.concept.slice(label.length + 1)
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
const byWeight = <T extends { level: ChangeLevel }>(a: T, b: T) => weight(b.level) - weight(a.level)

/** The summary of the comparison's Ontology Diff. */
export function summarizeChanges(comparison: OntologyComparison): ChangeSummary {
  const levels = comparison.diff.changes.map(levelOf)
  const counts = [...CHANGE_LEVELS]
    .reverse()
    .map((level) => ({ level, count: levels.filter((l) => l === level).length }))
    .filter((c) => c.count > 0)
  const owners: [OwnerKind, string][] = [
    ...comparison.ontology.node_types.map((n): [OwnerKind, string] => ['node_type', n.label]),
    ...comparison.ontology.relationship_types.map((r): [OwnerKind, string] => ['relationship_type', r.label]),
  ]
  const concepts = owners
    .flatMap(([kind, label]): ConceptChanges[] => {
      const statements = changesOfConcept(comparison, kind, label)
        .map((c) => statementOf(kind, label, c))
        .sort(byWeight)
      return statements.length === 0 ? [] : [{ kind, label, level: statements[0].level, statements }]
    })
    .sort((a, b) => byWeight(a, b) || compare(a.label, b.label) || compare(a.kind, b.kind))
  return { counts, concepts }
}

const compare = (a: string, b: string) => (a < b ? -1 : a > b ? 1 : 0)
