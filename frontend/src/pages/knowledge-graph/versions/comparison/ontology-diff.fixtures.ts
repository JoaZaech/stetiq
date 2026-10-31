/**
 * Ontology Diff changes for the comparison's tests, built from the fields the Diff states
 * (`wire.ontology_diff_to_json`). Each test gives the classification, as the server would
 * have decided it. A `detail` defaults to a plain placeholder; a test that shows one gives
 * it. No code under test reads it.
 */
import type {
  Classification,
  NodeTypeChange,
  OwnerKind,
  PropertyChange,
  RelationshipTypeChange,
} from '@/api/ontology-diff'
import { type Pattern, patternId } from '../concepts'

/** A change to a class or relation itself. */
export const conceptChange = (
  kind: OwnerKind,
  label: string,
  change: NodeTypeChange['kind'],
  classification: Classification,
  detail = `${label} ${change}`,
): NodeTypeChange | RelationshipTypeChange => ({ concept: label, concept_kind: kind, kind: change, classification, detail })

/** A change to attribute `attribute` of the class or relation `owner`; an added one is optional unless `required`. */
export const attributeChange = (
  ownerKind: OwnerKind,
  owner: string,
  attribute: string,
  change: PropertyChange['kind'],
  classification: Classification,
  { required = false, detail }: { required?: boolean; detail?: string } = {},
): PropertyChange => {
  const concept = `${owner}.${attribute}`
  const fields = {
    concept,
    concept_kind: 'property' as const,
    classification,
    detail: detail ?? `${concept} ${change}`,
    owner,
    owner_kind: ownerKind,
    attribute,
  }
  return change === 'added' ? { ...fields, kind: change, required } : { ...fields, kind: change }
}

/** A change to one of a relation's endpoint Patterns. */
export const endpointChange = (
  pattern: Pattern,
  classification: Classification,
  detail = `endpoint pattern ${patternId(pattern)} changed`,
): RelationshipTypeChange => ({
  concept: pattern[1],
  concept_kind: 'relationship_type',
  kind: 'changed',
  classification,
  detail,
  pattern,
})

/** A description changed on a class or relation itself, which the Diff classes cosmetic. */
export const conceptDescribed = (kind: OwnerKind, label: string) =>
  conceptChange(kind, label, 'changed', 'cosmetic', 'description changed')

/** A description changed on an attribute, which the Diff classes cosmetic. */
export const attributeDescribed = (ownerKind: OwnerKind, owner: string, attribute: string) =>
  attributeChange(ownerKind, owner, attribute, 'changed', 'cosmetic', { detail: 'description changed' })
