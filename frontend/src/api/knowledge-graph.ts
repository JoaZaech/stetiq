import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, kgPath } from './client'
import { knowledgeGraphsQueryKeys } from './knowledge-graphs'

/** One Knowledge Graph (wire.knowledge_graph_to_json). */
export interface KnowledgeGraph {
  name: string
  created_at: string
  /** Markdown; null when unset. */
  description: string | null
}

export type EvolutionMode = 'strict' | 'evolving'

/** Query keys about one Knowledge Graph itself. */
export const knowledgeGraphQueryKeys = {
  one: (name: string) => ['knowledge-graph', name] as const,
  evolutionMode: (name: string) => ['evolution-mode', name] as const,
}

export const knowledgeGraphQuery = (name: string) => ({
  queryKey: knowledgeGraphQueryKeys.one(name),
  queryFn: () => api<KnowledgeGraph>(kgPath(name)),
})

export const useKnowledgeGraph = (name: string) => useQuery(knowledgeGraphQuery(name))

/** Replace the markdown description (needs `edit`); a blank one clears it. */
export function useSetKnowledgeGraphDescription(name: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (description: string) =>
      api<KnowledgeGraph>(kgPath(name) + '/description', 'PUT', { description }),
    onSuccess: (kg) => {
      queryClient.setQueryData(knowledgeGraphQueryKeys.one(name), kg)
      void queryClient.invalidateQueries({ queryKey: knowledgeGraphsQueryKeys.all() })
    },
  })
}

export const evolutionModeQuery = (name: string) => ({
  queryKey: knowledgeGraphQueryKeys.evolutionMode(name),
  queryFn: async () => (await api<{ mode: EvolutionMode }>(kgPath(name) + '/evolution-mode')).mode,
})

export const useEvolutionMode = (name: string) => useQuery(evolutionModeQuery(name))
