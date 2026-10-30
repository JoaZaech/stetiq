import { useQuery } from '@tanstack/react-query'
import { api } from './client'

/** A Construction Run's status (entities.RunStatus). */
export type RunStatus = 'running' | 'finished' | 'failed'

/**
 * A Knowledge Graph (wire.knowledge_graph_to_json). The summary fields are filled in
 * only by the list; they are null elsewhere, and absent from older servers.
 */
export interface KnowledgeGraph {
  name: string
  created_at: string
  /** The Ontology Version the Contract Alias points to. */
  contract_version?: number | null
  /** The newest Ontology Version. */
  latest_version?: number | null
  /** Status of the most recently started Construction Run; null without runs. */
  last_run_status?: RunStatus | null
  /** Time of the latest recorded change to the Knowledge Graph. */
  last_modified_at?: string | null
}

/** GET /knowledge-graphs: those the user can read, by name, with their summaries. */
export const knowledgeGraphsQuery = {
  queryKey: ['knowledge-graphs'],
  queryFn: () => api<KnowledgeGraph[]>('/knowledge-graphs'),
} as const

export function useKnowledgeGraphs() {
  return useQuery(knowledgeGraphsQuery)
}
