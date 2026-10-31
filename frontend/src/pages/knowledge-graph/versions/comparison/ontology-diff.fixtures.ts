/**
 * Ontology Diff changes for the comparison's tests, built from the fields the Diff states
 * (`wire.ontology_diff_to_json`). Each `detail` is worded as `ontology/diff.py` words it,
 * for the tests that show it; no code under test reads it.
 */
import type { Classification, OntologyChange, OwnerKind } from '@/api/ontology-diff'
import { type Pattern, patternId } from '../concepts'

type ChangeKind = OntologyChange['kind']

const DIFF_NOUN: Record<OwnerKind, string> = { node_type: 'node type', relationship_type: 'relationship type' }

/** A change to a class or relation itself; `detail` defaults to the Diff's for added and removed. */
export const conceptChange = (
  kind: OwnerKind,
  label: string,
  change: ChangeKind,
  classification: Classification,
  detail = `${DIFF_NOUN[kind]} ${label} ${change}`,
): OntologyChange => ({ concept: label, concept_kind: kind, kind: change, classification, detail })

/** A change to attribute `attribute` of the class or relation `owner`. */
export const attributeChange = (
  ownerKind: OwnerKind,
  owner: string,
  attribute: string,
  change: ChangeKind,
  classification: Classification,
  { required, detail }: { required?: boolean; detail?: string } = {},
): OntologyChange => {
  const concept = `${owner}.${attribute}`
  return {
    concept,
    concept_kind: 'property',
    kind: change,
    classification,
    detail:
      detail ??
      (change === 'added' ? `${required ? 'required' : 'optional'} property ${concept} added` : `property ${concept} ${change}`),
    owner,
    owner_kind: ownerKind,
    attribute,
    ...(change === 'added' && { required: required ?? false }),
  }
}

/** A relation's endpoint Pattern added (additive) or removed (breaking). */
export const endpointChange = (pattern: Pattern, change: 'added' | 'removed'): OntologyChange => ({
  concept: pattern[1],
  concept_kind: 'relationship_type',
  kind: 'changed',
  classification: change === 'added' ? 'additive' : 'breaking',
  detail: `endpoint pattern ${patternId(pattern)} ${change}`,
  pattern,
})

/** A description changed on a class or relation itself: cosmetic. */
export const conceptDescribed = (kind: OwnerKind, label: string): OntologyChange =>
  conceptChange(kind, label, 'changed', 'cosmetic', 'description changed')

/** A description changed on an attribute: cosmetic. */
export const attributeDescribed = (ownerKind: OwnerKind, owner: string, attribute: string): OntologyChange =>
  attributeChange(ownerKind, owner, attribute, 'changed', 'cosmetic', { detail: 'description changed' })
