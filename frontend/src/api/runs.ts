import { useQuery } from '@tanstack/react-query'
import { api, kgPath } from './client'
import type { EvaluationResult } from './ontology-versions'

/** wire.run_to_json */
export interface ConstructionRun {
  id: string
  knowledge_graph: string
  /** The Declared Ontology's version number. */
  ontology_version: number
  status: 'running' | 'finished' | 'failed'
  started_at: string
  ended_at: string | null
  params: Record<string, string>
  metrics: Record<string, number>
  observation_id: string | null
  conformance: Conformance | null
  /** The Candidate Ontology Version this run gave rise to. */
  candidate_version: number | null
}

export const runsQuery = (kg: string) => ({
  queryKey: ['runs', kg],
  queryFn: () => api<ConstructionRun[]>(kgPath(kg) + '/runs'),
})
export const useRuns = (kg: string) => useQuery(runsQuery(kg))

/** What a Conformance mismatch is about: a Concept, or an endpoint pattern (`conformance.MismatchSubjectKind`). */
export type MismatchSubjectKind = 'node_type' | 'relationship_type' | 'property' | 'pattern'

/** conformance.Mismatch */
export interface Mismatch {
  /** e.g. `Ticket`, `Ticket.priority`, `(Customer)-[OPENED]->(Ticket)` */
  subject: string
  subject_kind: MismatchSubjectKind
  /** `absent`: declared, not observed; `undeclared`: observed, not declared. */
  kind: 'absent' | 'undeclared' | 'type_mismatch' | 'required_missing'
  detail: string
}

/** conformance.Conformance.to_dict */
export interface Conformance {
  /** In [0, 1]: the share of checked items that conform. */
  score: number
  mismatches: Mismatch[]
}

/** GET /runs/<id>: 404 for an unknown run or one of a Knowledge Graph the user can't read. */
export const runQuery = (runId: string) => ({
  queryKey: ['run', runId],
  queryFn: () => api<ConstructionRun>(`/runs/${encodeURIComponent(runId)}`),
})
export const useRun = (runId: string) => useQuery(runQuery(runId))

/** The run's Evaluator results, the latest per Evaluator. */
export const runEvaluationsQuery = (kg: string, runId: string) => ({
  queryKey: ['run-evaluations', kg, runId],
  queryFn: () =>
    api<EvaluationResult[]>(`${kgPath(kg)}/runs/${encodeURIComponent(runId)}/evaluations`),
})
export const useRunEvaluations = (kg: string, runId: string) =>
  useQuery(runEvaluationsQuery(kg, runId))

/** wire.observation_to_json; the run page reads only the Observed Schema's sizes. */
export interface RunObservation {
  id: string
  knowledge_graph: string
  run_id: string | null
  observed_at: string
  /** GraphSourceScope.to_dict */
  scope: { database: string; label: string | null; namespace: string | null }
  schema: { node_types: unknown[]; relationship_types: unknown[]; patterns: unknown[] }
}

/** The Observation a run ended with (`run.observation_id`); idle while there is none. */
export const useRunObservation = (observationId: string | null) =>
  useQuery({
    queryKey: ['observation', observationId],
    queryFn: () => api<RunObservation>(`/observations/${encodeURIComponent(observationId ?? '')}`),
    enabled: observationId !== null,
  })
