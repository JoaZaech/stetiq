import { useQuery } from '@tanstack/react-query'
import { api } from './client'

import type { KnowledgeGraph } from './knowledge-graph'
import type { RunStatus } from './runs'

/**
 * A listed Knowledge Graph with a summary of its state
 * (wire.knowledge_graph_summary_to_json). Older servers leave the summary fields out.
 */
export interface KnowledgeGraphSummary extends KnowledgeGraph {
  /** The Ontology Version the Contract Alias points to. */
  contract_version?: number | null
  /** The newest Ontology Version. */
  latest_version?: number | null
  /** Status of the most recently started Construction Run; null without runs. */
  last_run_status?: RunStatus | null
  /** Time of the latest recorded change to the Knowledge Graph. */
  last_modified_at?: string | null
}

/** Query keys of the Knowledge Graph list: invalidate after a write that changes a summary. */
export const knowledgeGraphsQueryKeys = {
  all: () => ['knowledge-graphs'] as const,
}

/** GET /knowledge-graphs: those the user can read, by name, with their summaries. */
export const knowledgeGraphsQuery = {
  queryKey: knowledgeGraphsQueryKeys.all(),
  queryFn: () => api<KnowledgeGraphSummary[]>('/knowledge-graphs'),
} as const

export function useKnowledgeGraphs() {
  return useQuery(knowledgeGraphsQuery)
}
