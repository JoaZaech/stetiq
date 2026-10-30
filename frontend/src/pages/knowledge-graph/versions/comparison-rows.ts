/**
 * The rows of a comparison's Table: one per Ontology Diff change, with the level it
 * weighs at in the comparison (documentation-only its own) and where it is on the Map.
 */
import type { OntologyChange } from '@/api/ontology-diff'
import { changesOfConcept, type OntologyComparison, type OwnerKind } from './ontology-map-comparison'
import { CHANGE_LEVELS, type ChangeLevel, levelOf } from './ontology-map-summary'
import type { TableConcept } from './table-links'

/** What kind of Concept a change is to, in the Table's words. */
export type ComparisonConceptKind = 'class' | 'relation' | 'attribute'

const CONCEPT_KIND: Record<OntologyChange['concept_kind'], ComparisonConceptKind> = {
  node_type: 'class',
  relationship_type: 'relation',
  property: 'attribute',
}

const TABLE_KIND: Record<OwnerKind, TableConcept['kind']> = { node_type: 'class', relationship_type: 'relation' }

/** One Diff change, as a row of the comparison's Table. */
export interface ComparisonRow {
  /** Tells the row apart from every other: a Concept may change more than once. */
  id: string
  /** The class or relation label, or `<owner>.<attribute>`. */
  concept: string
  conceptKind: ComparisonConceptKind
  change: OntologyChange['kind']
  level: ChangeLevel
  detail: string
  /** The class or relation to show on the Map: the Concept itself, or an attribute's owner. */
  owner: TableConcept | null
}

/** Where `change` is on the Map: its class or relation, or the one owning the attribute. */
function ownerOf(comparison: OntologyComparison, change: OntologyChange): TableConcept | null {
  if (change.concept_kind !== 'property') return { kind: TABLE_KIND[change.concept_kind], label: change.concept }
  const label = change.concept.slice(0, change.concept.indexOf('.'))
  // A class and a relation may share a label: the one whose attribute changed.
  const kind = (['node_type', 'relationship_type'] as const).find((k) =>
    changesOfConcept(comparison, k, label).includes(change),
  )
  return kind ? { kind: TABLE_KIND[kind], label } : null
}

/** The comparison's Diff changes as rows, the weightiest first, otherwise in the Diff's order. */
export function comparisonRows(comparison: OntologyComparison): ComparisonRow[] {
  const rows = comparison.diff.changes.map(
    (change, i): ComparisonRow => ({
      id: String(i),
      concept: change.concept,
      conceptKind: CONCEPT_KIND[change.concept_kind],
      change: change.kind,
      level: levelOf(comparison, change),
      detail: change.detail,
      owner: ownerOf(comparison, change),
    }),
  )
  return rows.sort((a, b) => CHANGE_LEVELS.indexOf(b.level) - CHANGE_LEVELS.indexOf(a.level))
}
