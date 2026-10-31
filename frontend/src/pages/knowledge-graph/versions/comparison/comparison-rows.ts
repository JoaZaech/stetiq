/**
 * The rows of a comparison's Table: one per Ontology Diff change, with the level it
 * weighs at (its classification) and where it is on the Map.
 */
import { type Classification, compareSeverity, type OntologyChange } from '@/api/ontology-diff'
import { type ClassOrRelation, CONCEPT_NOUN, type ConceptNoun } from '../concepts'
import type { OntologyComparison } from './ontology-map-comparison'

/** One Diff change, as a row of the comparison's Table. */
export interface ComparisonRow {
  /** Tells the row apart from every other: a Concept may change more than once. */
  id: string
  /** The class or relation label, or `<owner>.<attribute>`. */
  concept: string
  /** What kind of Concept it changed, in the Table's words. */
  conceptKind: ConceptNoun
  change: OntologyChange['kind']
  level: Classification
  detail: string
  /** The class or relation to show on the Map: the Concept itself, or an attribute's owner. */
  owner: ClassOrRelation
}

/** Where `change` is on the Map: its class or relation, or the one the Diff says owns the attribute. */
function ownerOf(change: OntologyChange): ClassOrRelation {
  return change.concept_kind === 'property'
    ? { kind: CONCEPT_NOUN[change.owner_kind], label: change.owner }
    : { kind: CONCEPT_NOUN[change.concept_kind], label: change.concept }
}

/** The comparison's Diff changes as rows, the weightiest first, otherwise in the Diff's order. */
export function comparisonRows(comparison: OntologyComparison): ComparisonRow[] {
  const rows = comparison.diff.changes.map(
    (change, i): ComparisonRow => ({
      id: String(i),
      concept: change.concept,
      conceptKind: CONCEPT_NOUN[change.concept_kind],
      change: change.kind,
      level: change.classification,
      detail: change.detail,
      owner: ownerOf(change),
    }),
  )
  return rows.sort((a, b) => compareSeverity(b.level, a.level))
}
