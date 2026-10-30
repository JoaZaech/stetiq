import { useQuery } from '@tanstack/react-query'
import { api, kgPath } from './client'

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
  conformance: Record<string, unknown> | null
  /** The Candidate Ontology Version this run gave rise to. */
  candidate_version: number | null
}

export const runsQuery = (kg: string) => ({
  queryKey: ['runs', kg],
  queryFn: () => api<ConstructionRun[]>(kgPath(kg) + '/runs'),
})
export const useRuns = (kg: string) => useQuery(runsQuery(kg))
