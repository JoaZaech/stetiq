import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, kgPath } from './client'

/** One Knowledge Graph (wire.knowledge_graph_to_json). */
export interface KnowledgeGraph {
  name: string
  created_at: string
  /** Markdown; null when unset. */
  description: string | null
}

export type EvolutionMode = 'strict' | 'evolving'

export const knowledgeGraphQuery = (name: string) => ({
  queryKey: ['knowledge-graph', name],
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
      queryClient.setQueryData(knowledgeGraphQuery(name).queryKey, kg)
      void queryClient.invalidateQueries({ queryKey: ['knowledge-graphs'] })
    },
  })
}

export const evolutionModeQuery = (name: string) => ({
  queryKey: ['evolution-mode', name],
  queryFn: async () => (await api<{ mode: EvolutionMode }>(kgPath(name) + '/evolution-mode')).mode,
})

export const useEvolutionMode = (name: string) => useQuery(evolutionModeQuery(name))
