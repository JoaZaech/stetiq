import { useQuery } from '@tanstack/react-query'
import { api, kgPath } from './client'

/** Consumer impact of a change, from least to most severe (ontology/diff.py). */
export const CLASSIFICATIONS = ['additive', 'deprecating', 'breaking'] as const

export type Classification = (typeof CLASSIFICATIONS)[number]

/** One change to one Concept (wire.ontology_diff_to_json). */
export interface OntologyChange {
  /** A class or relation label, or `<owner>.<attribute>`. */
  concept: string
  concept_kind: 'node_type' | 'relationship_type' | 'property'
  kind: 'added' | 'removed' | 'changed' | 'deprecated'
  classification: Classification
  detail: string
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
