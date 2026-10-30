/**
 * The rows of a comparison's Table: one per Ontology Diff change, with the level it
 * weighs at in the comparison (documentation-only its own) and where it is on the Map.
 */
import type { OntologyChange } from '@/api/ontology-diff'
import { attributeReference, type ClassOrRelation, CONCEPT_NOUN, type ConceptNoun } from '../concepts'
import { changesOfConcept, type OntologyComparison } from './ontology-map-comparison'
import { type ChangeLevel, compareLevels, levelOf } from './ontology-map-summary'

/** One Diff change, as a row of the comparison's Table. */
export interface ComparisonRow {
  /** Tells the row apart from every other: a Concept may change more than once. */
  id: string
  /** The class or relation label, or `<owner>.<attribute>`. */
  concept: string
  /** What kind of Concept it changed, in the Table's words. */
  conceptKind: ConceptNoun
  change: OntologyChange['kind']
  level: ChangeLevel
  detail: string
  /** The class or relation to show on the Map: the Concept itself, or an attribute's owner. */
  owner: ClassOrRelation | null
}

/** Where `change` is on the Map: its class or relation, or the one owning the attribute. */
function ownerOf(comparison: OntologyComparison, change: OntologyChange): ClassOrRelation | null {
  if (change.concept_kind !== 'property') return { kind: CONCEPT_NOUN[change.concept_kind], label: change.concept }
  const label = attributeReference(change.concept).owner
  // A class and a relation may share a label: the one whose attribute changed.
  const kind = (['node_type', 'relationship_type'] as const).find((k) =>
    changesOfConcept(comparison, k, label).includes(change),
  )
  return kind ? { kind: CONCEPT_NOUN[kind], label } : null
}

/** The comparison's Diff changes as rows, the weightiest first, otherwise in the Diff's order. */
export function comparisonRows(comparison: OntologyComparison): ComparisonRow[] {
  const rows = comparison.diff.changes.map(
    (change, i): ComparisonRow => ({
      id: String(i),
      concept: change.concept,
      conceptKind: CONCEPT_NOUN[change.concept_kind],
      change: change.kind,
      level: levelOf(comparison, change),
      detail: change.detail,
      owner: ownerOf(comparison, change),
    }),
  )
  return rows.sort((a, b) => compareLevels(b.level, a.level))
}
