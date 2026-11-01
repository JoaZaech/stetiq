import type { ConceptKind } from '@/api/ontology-diff'
import type { MismatchSubjectKind } from '@/api/runs'

/**
 * Each kind of Concept in the glossary's words, by its wire value (`ConceptKind`, a
 * mismatch's or Drift finding's `subject_kind`) and by the Map's and the Table's own
 * name for it. A pattern isn't a Concept, so it stays lower case.
 */
const CONCEPT_KIND_WORD = {
  node_type: 'Class',
  class: 'Class',
  relationship_type: 'Relation',
  relation: 'Relation',
  property: 'Attribute',
  attribute: 'Attribute',
  vocabulary: 'Vocabulary',
  pattern: 'pattern',
} as const satisfies Record<ConceptKind | MismatchSubjectKind | 'class' | 'relation' | 'attribute', string>

/** A Concept kind as the server sends it or the Map and the Table name it. */
export type ConceptKindValue = keyof typeof CONCEPT_KIND_WORD

/**
 * How the UI names a kind of Concept: `node_type` → Class, `relationship_type` →
 * Relation, `property` → Attribute; never "node type", "relationship type" or
 * "property". Display only: the wire values stay as they are.
 */
export function conceptKindLabel(kind: ConceptKindValue): string {
  return CONCEPT_KIND_WORD[kind]
}
