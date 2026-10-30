import { useQuery } from '@tanstack/react-query'
import { api, kgPath } from './client'

/** The canonical Ontology dict (ontology/canonical.py `to_dict`): defaults are omitted. */
export interface OntologyProperty {
  name: string
  type: string
  description?: string
  required?: boolean
}

export interface OntologyConcept {
  label: string
  description?: string
  properties?: OntologyProperty[]
  deprecated?: boolean
  replacedBy?: string
  /** Superclass; node types only. */
  parent?: string
}

export interface OntologyConstraint {
  type: string
  node_type: string
  property_name: string
}

export interface Ontology {
  node_types: OntologyConcept[]
  relationship_types: OntologyConcept[]
  /** `[source, relationship, target]` */
  patterns: [string, string, string][]
  constraints?: OntologyConstraint[]
}

/** wire.ontology_version_to_json */
export interface OntologyVersion {
  knowledge_graph: string
  number: number
  content_hash: string
  /** `registered` by hand, or `run`: a Candidate created by a Construction Run. */
  origin: 'registered' | 'run'
  created_at: string
  ontology: Ontology
}

/** wire.evaluation_result_to_json; the latest result per (evaluator, parameters). */
export interface EvaluationResult {
  knowledge_graph: string
  subject_kind: 'ontology_version' | 'construction_run'
  subject_id: string
  evaluator: string
  metrics: Record<string, number>
  details: { item: string; message: string; metric: string; data?: Record<string, unknown> }[]
  created_at: string
  parameters: Record<string, unknown>
  use_case_version: number | null
}

const versionsPath = (kg: string) => kgPath(kg) + '/ontology-versions'

/** Oldest first, as the server returns them. */
export const ontologyVersionsQuery = (kg: string) => ({
  queryKey: ['ontology-versions', kg],
  queryFn: () => api<OntologyVersion[]>(versionsPath(kg)),
})
export const useOntologyVersions = (kg: string) => useQuery(ontologyVersionsQuery(kg))

export const ontologyVersionQuery = (kg: string, number: number) => ({
  queryKey: ['ontology-versions', kg, number],
  queryFn: () => api<OntologyVersion>(`${versionsPath(kg)}/${number}`),
})
export const useOntologyVersion = (kg: string, number: number) =>
  useQuery({ ...ontologyVersionQuery(kg, number), enabled: Number.isInteger(number) })

export const versionEvaluationsQuery = (kg: string, number: number) => ({
  queryKey: ['ontology-versions', kg, number, 'evaluations'],
  queryFn: () => api<EvaluationResult[]>(`${versionsPath(kg)}/${number}/evaluations`),
})
export const useVersionEvaluations = (kg: string, number: number) =>
  useQuery(versionEvaluationsQuery(kg, number))
