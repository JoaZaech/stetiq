import { useQuery } from '@tanstack/react-query'
import { api, kgPath } from './client'

/** One Knowledge Graph (wire.knowledge_graph_to_json). */
export interface KnowledgeGraph {
  name: string
  created_at: string
  /** Markdown; added to the wire by a later ticket (#31), absent until then. */
  description?: string | null
}

export type EvolutionMode = 'strict' | 'evolving'

export const knowledgeGraphQuery = (name: string) => ({
  queryKey: ['knowledge-graph', name],
  queryFn: () => api<KnowledgeGraph>(kgPath(name)),
})

export const useKnowledgeGraph = (name: string) => useQuery(knowledgeGraphQuery(name))

export const evolutionModeQuery = (name: string) => ({
  queryKey: ['evolution-mode', name],
  queryFn: async () => (await api<{ mode: EvolutionMode }>(kgPath(name) + '/evolution-mode')).mode,
})

export const useEvolutionMode = (name: string) => useQuery(evolutionModeQuery(name))
