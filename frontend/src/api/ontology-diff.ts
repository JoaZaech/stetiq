import { useQuery } from '@tanstack/react-query'
import { api, kgPath } from './client'

/**
 * Consumer impact of a change, from least to most severe (ontology/diff.py). A cosmetic
 * change touches only documentation (a description).
 */
export const CLASSIFICATIONS = ['cosmetic', 'additive', 'deprecating', 'breaking'] as const

export type Classification = (typeof CLASSIFICATIONS)[number]

/**
 * What "more severe" means, everywhere: orders classifications from the least to the most
 * severe, cosmetic first (a sort comparator). Sort with `(a, b) => compareSeverity(b, a)`
 * for the most severe first.
 */
export const compareSeverity = (a: Classification, b: Classification): number =>
  CLASSIFICATIONS.indexOf(a) - CLASSIFICATIONS.indexOf(b)

/** The most severe of `classifications`, or null for none. */
export const mostSevere = (classifications: Iterable<Classification>): Classification | null =>
  [...classifications].reduce<Classification | null>((a, c) => (a === null || compareSeverity(c, a) > 0 ? c : a), null)

/** Every classification, the most severe first. */
export const MOST_SEVERE_FIRST: readonly Classification[] = [...CLASSIFICATIONS].sort((a, b) => compareSeverity(b, a))

/**
 * How the UI names each classification. Cosmetic changes (only a description changed)
 * are "documentation-only" here, as the comparison has always called them.
 */
export const CLASSIFICATION_LABEL: Record<Classification, string> = {
  cosmetic: 'documentation-only',
  additive: 'additive',
  deprecating: 'deprecating',
  breaking: 'breaking',
}

/** What kind of Concept: a class, a relation or an attribute (`ConceptKind` in ontology/model.py). */
export type ConceptKind = 'node_type' | 'relationship_type' | 'property'

/** A class's or a relation's Concept kind: the Concepts that own attributes. */
export type OwnerKind = Exclude<ConceptKind, 'property'>

/**
 * One change to one Concept (wire.ontology_diff_to_json). The fields after `detail` state
 * what it concerns, present only when it concerns one (and absent from an older server's).
 */
export interface OntologyChange {
  /** A class or relation label, or `<owner>.<attribute>`. */
  concept: string
  concept_kind: ConceptKind
  kind: 'added' | 'removed' | 'changed' | 'deprecated'
  classification: Classification
  /** The change in words, for people only: shown, never read by code. */
  detail: string
  /** An attribute change's owner, its kind and the attribute's name. */
  owner?: string
  owner_kind?: OwnerKind
  attribute?: string
  /** Whether an added attribute is required. */
  required?: boolean
  /** The Pattern an endpoint change adds or removes: source, relation, target. */
  pattern?: [string, string, string]
}

/** The Ontology Diff between two Ontology Versions of one Knowledge Graph. */
export interface OntologyDiff {
  /** The most severe change's classification; null when nothing changed. */
  classification: Classification | null
  changes: OntologyChange[]
}

/** `GET …/ontology-diff?base=&target=`: what changed from version `base` to `target`. */
export const ontologyDiffQueryKeys = {
  one: (kg: string, base: number, target: number) => ['ontology-diff', kg, base, target] as const,
}

export const ontologyDiffQuery = (kg: string, base: number, target: number) => ({
  queryKey: ontologyDiffQueryKeys.one(kg, base, target),
  queryFn: () => api<OntologyDiff>(`${kgPath(kg)}/ontology-diff?base=${base}&target=${target}`),
})
export const useOntologyDiff = (kg: string, base: number, target: number) =>
  useQuery({
    ...ontologyDiffQuery(kg, base, target),
    enabled: Number.isInteger(base) && Number.isInteger(target),
  })
