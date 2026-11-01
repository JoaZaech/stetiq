import { useQuery } from '@tanstack/react-query'
import { api, kgPath } from './client'
import type { ConsumerGate } from './use-cases'

/** Why a question has no row change (`consumer_gates.MissingInput`). */
export type MissingInput =
  | 'no_baseline_run'
  | 'baseline_missing'
  | 'baseline_error'
  | 'candidate_missing'
  | 'candidate_error'

/**
 * A failing Competency Question of a `row_count_drop` Consumer Gate, as fields
 * (`consumer_gates.RowCountFinding`). `change` is relative, negative for a drop; `limit`
 * is the gate's `max_drop`. Each optional field is sent only when it applies.
 */
export interface RowCountFinding {
  task: string
  competency_question: string
  limit: number
  before?: number
  after?: number
  change?: number
  missing?: MissingInput
}

export interface ConsumerGateOutcome {
  gate: ConsumerGate
  passed: boolean
  /** For people; the UI renders `findings`, and shows these only when there are none. */
  reasons: string[]
  findings: RowCountFinding[]
}

/** codec.consumer_gate_result_to_json: one Consumer's recorded Consumer Gate evaluation. */
export interface ConsumerGateResult {
  knowledge_graph: string
  consumer: string
  use_case_version: number
  /** The finished Construction Run judged, and the Ontology Version it stands for. */
  run_id: string
  ontology_version: number
  /** The baseline run, on the Contract Alias's version; null when there was none. */
  baseline_run_id: string | null
  baseline_ontology_version: number
  passed: boolean
  outcomes: ConsumerGateOutcome[]
  evaluated_at: string
}

export const consumerGateResultQueryKeys = {
  all: (kg: string) => ['consumer-gate-results', kg] as const,
}

/** Every recorded Consumer Gate result of the Knowledge Graph, oldest first. */
export const consumerGateResultsQuery = (kg: string) => ({
  queryKey: consumerGateResultQueryKeys.all(kg),
  queryFn: () => api<ConsumerGateResult[]>(kgPath(kg) + '/consumer-gate-results'),
})
export const useConsumerGateResults = (kg: string) => useQuery(consumerGateResultsQuery(kg))

/** `consumer`'s most recent recorded result (results come oldest first), if any. */
export function latestConsumerGateResult(
  results: readonly ConsumerGateResult[],
  consumer: string,
): ConsumerGateResult | undefined {
  return results.filter((r) => r.consumer === consumer).at(-1)
}
