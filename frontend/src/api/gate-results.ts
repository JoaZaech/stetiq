import { useQuery } from '@tanstack/react-query'
import { api, kgPath } from './client'

/** wire.gate_result_to_json: one Gate evaluation, computed and recorded by the server. */
export interface GateResult {
  knowledge_graph: string
  subject_kind: 'ontology_version' | 'construction_run'
  subject_id: string
  ontology_version: number
  passed: boolean
  outcomes: { gate: Record<string, unknown> & { name: string }; passed: boolean; reasons: string[] }[]
  evaluated_at: string
}

export const gateResultQueryKeys = {
  all: (kg: string) => ['gate-results', kg] as const,
}

export const gateResultsQuery = (kg: string) => ({
  queryKey: gateResultQueryKeys.all(kg),
  queryFn: () => api<GateResult[]>(kgPath(kg) + '/gate-results'),
})
export const useGateResults = (kg: string) => useQuery(gateResultsQuery(kg))

/** The most recent Gate result about one subject, or undefined when it was never gated. */
export function latestGateResult(
  results: readonly GateResult[],
  subjectKind: GateResult['subject_kind'],
  subjectId: string,
): GateResult | undefined {
  return results
    .filter((r) => r.subject_kind === subjectKind && r.subject_id === subjectId)
    .reduce<GateResult | undefined>(
      (latest, r) => (latest === undefined || r.evaluated_at >= latest.evaluated_at ? r : latest),
      undefined,
    )
}
