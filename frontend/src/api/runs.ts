import { useQuery } from '@tanstack/react-query'
import { api, kgPath } from './client'
import type { EvaluationResult } from './ontology-versions'

/** A Construction Run's status (entities.RunStatus). */
export type RunStatus = 'running' | 'finished' | 'failed'

/** wire.run_to_json */
export interface ConstructionRun {
  id: string
  knowledge_graph: string
  /** The Declared Ontology's version number. */
  ontology_version: number
  status: RunStatus
  started_at: string
  ended_at: string | null
  params: Record<string, string>
  metrics: Record<string, number>
  observation_id: string | null
  conformance: Conformance | null
  /** The Candidate Ontology Version this run gave rise to. */
  candidate_version: number | null
}

/**
 * Query keys of Construction Runs and their Evaluator results. Every key about a
 * Knowledge Graph's run Evaluator results starts with `allEvaluations(kg)`.
 */
export const runQueryKeys = {
  all: (kg: string) => ['runs', kg] as const,
  one: (runId: string) => ['run', runId] as const,
  allEvaluations: (kg: string) => ['run-evaluations', kg] as const,
  evaluations: (kg: string, runId: string) => ['run-evaluations', kg, runId] as const,
}

export const runsQuery = (kg: string) => ({
  queryKey: runQueryKeys.all(kg),
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
  queryKey: runQueryKeys.one(runId),
  queryFn: () => api<ConstructionRun>(`/runs/${encodeURIComponent(runId)}`),
})
export const useRun = (runId: string) => useQuery(runQuery(runId))

/** The run's Evaluator results, the latest per Evaluator. */
export const runEvaluationsQuery = (kg: string, runId: string) => ({
  queryKey: runQueryKeys.evaluations(kg, runId),
  queryFn: () =>
    api<EvaluationResult[]>(`${kgPath(kg)}/runs/${encodeURIComponent(runId)}/evaluations`),
})
export const useRunEvaluations = (kg: string, runId: string) =>
  useQuery(runEvaluationsQuery(kg, runId))

/**
 * `GET …/evaluations?subject_kind=construction_run`: the latest Evaluator results of
 * every run in one request (`subject_id` is the run id).
 */
export const allRunEvaluationsQuery = (kg: string) => ({
  queryKey: runQueryKeys.allEvaluations(kg),
  queryFn: () => api<EvaluationResult[]>(kgPath(kg) + '/evaluations?subject_kind=construction_run'),
})
export const useAllRunEvaluations = (kg: string) => useQuery(allRunEvaluationsQuery(kg))
