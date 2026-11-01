import { useQuery } from '@tanstack/react-query'
import { api, kgPath } from './client'

/**
 * The Ontology on the wire (tracking/codec.py `ontology_to_json`): the canonical dict, with
 * defaults omitted and each Definition under `definition`.
 */
export interface OntologyProperty {
  name: string
  type: string
  definition?: string
  required?: boolean
  /** The label of the Vocabulary this STRING attribute is bound to. */
  vocabulary?: string
}

/** A Vocabulary and its Vocabulary Values, each identified by its label. */
export interface OntologyVocabulary {
  label: string
  definition?: string
  values: { label: string; definition?: string; deprecated?: boolean; replacedBy?: string }[]
}

export interface OntologyConcept {
  label: string
  definition?: string
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
  vocabularies?: OntologyVocabulary[]
}

/** The mapping form the canonical dict uses for a pattern that declares a cardinality. */
interface BoundedPattern {
  source: string
  relationship: string
  target: string
  cardinality: Partial<Record<'out' | 'in', { min?: number; max?: number }>>
}

/**
 * An Ontology Version as the server sends it. The UI does not show cardinality yet, so
 * `withPatternTriples` reduces every pattern to its triple before the UI sees it.
 */
export interface WireOntologyVersion extends Omit<OntologyVersion, 'ontology'> {
  ontology: Omit<Ontology, 'patterns'> & { patterns: (Ontology['patterns'][number] | BoundedPattern)[] }
}

export const withPatternTriples = <V extends WireOntologyVersion>(
  version: V,
): Omit<V, 'ontology'> & { ontology: Ontology } => ({
  ...version,
  ontology: {
    ...version.ontology,
    patterns: version.ontology.patterns.map((p) =>
      Array.isArray(p) ? p : ([p.source, p.relationship, p.target] as [string, string, string]),
    ),
  },
})

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

/** An item of the version list, which also says whether the version is a Candidate. */
export interface ListedOntologyVersion extends OntologyVersion {
  /** No Alias has pointed to it yet, as the server decides. Absent from older servers. */
  candidate?: boolean
}

const versionsPath = (kg: string) => kgPath(kg) + '/ontology-versions'

/**
 * Query keys of Ontology Versions and their Evaluator results. Every key about a
 * Knowledge Graph's versions starts with `all(kg)`, so invalidating it refreshes them all.
 */
export const ontologyVersionQueryKeys = {
  all: (kg: string) => ['ontology-versions', kg] as const,
  one: (kg: string, number: number) => ['ontology-versions', kg, number] as const,
  evaluations: (kg: string, number: number) => ['ontology-versions', kg, number, 'evaluations'] as const,
  allEvaluations: (kg: string) => ['ontology-versions', kg, 'evaluations'] as const,
}

/** Oldest first, as the server returns them. */
export const ontologyVersionsQuery = (kg: string) => ({
  queryKey: ontologyVersionQueryKeys.all(kg),
  queryFn: async (): Promise<ListedOntologyVersion[]> =>
    (await api<(WireOntologyVersion & { candidate?: boolean })[]>(versionsPath(kg))).map(
      withPatternTriples,
    ),
})
export const useOntologyVersions = (kg: string) => useQuery(ontologyVersionsQuery(kg))

/**
 * `GET …/evaluations?subject_kind=ontology_version`: the latest results of every version
 * in one request (`subject_id` is the version number).
 */
export const allVersionEvaluationsQuery = (kg: string) => ({
  queryKey: ontologyVersionQueryKeys.allEvaluations(kg),
  queryFn: () => api<EvaluationResult[]>(kgPath(kg) + '/evaluations?subject_kind=ontology_version'),
})
export const useAllVersionEvaluations = (kg: string) => useQuery(allVersionEvaluationsQuery(kg))

export const ontologyVersionQuery = (kg: string, number: number) => ({
  queryKey: ontologyVersionQueryKeys.one(kg, number),
  queryFn: async (): Promise<OntologyVersion> =>
    withPatternTriples(await api<WireOntologyVersion>(`${versionsPath(kg)}/${number}`)),
})
export const useOntologyVersion = (kg: string, number: number) =>
  useQuery({ ...ontologyVersionQuery(kg, number), enabled: Number.isInteger(number) })

export const versionEvaluationsQuery = (kg: string, number: number) => ({
  queryKey: ontologyVersionQueryKeys.evaluations(kg, number),
  queryFn: () => api<EvaluationResult[]>(`${versionsPath(kg)}/${number}/evaluations`),
})
export const useVersionEvaluations = (kg: string, number: number) =>
  useQuery(versionEvaluationsQuery(kg, number))
