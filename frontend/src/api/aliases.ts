import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, kgPath } from './client'
import { knowledgeGraphsQueryKeys } from './knowledge-graphs'

/** wire.alias_to_json */
export interface Alias {
  knowledge_graph: string
  name: string
  version: number
  updated_at: string
}

/** wire.promotion_to_json: one move of an Alias, as audited. */
export interface Promotion {
  knowledge_graph: string
  alias: string
  from_version: number | null
  to_version: number
  actor: string
  promoted_at: string
  gate_result: 'passed' | 'failed' | null
}

/** Query keys of a Knowledge Graph's Aliases and their audit log. */
export const aliasQueryKeys = {
  aliases: (kg: string) => ['aliases', kg] as const,
  contractAlias: (kg: string) => ['contract-alias', kg] as const,
  promotions: (kg: string) => ['promotions', kg] as const,
}

export const aliasesQuery = (kg: string) => ({
  queryKey: aliasQueryKeys.aliases(kg),
  queryFn: () => api<Alias[]>(kgPath(kg) + '/aliases'),
})
export const useAliases = (kg: string) => useQuery(aliasesQuery(kg))

/** The name of the Contract Alias (default `production`). */
export const contractAliasQuery = (kg: string) => ({
  queryKey: aliasQueryKeys.contractAlias(kg),
  queryFn: async () => (await api<{ alias: string }>(kgPath(kg) + '/contract-alias')).alias,
})
export const useContractAlias = (kg: string) => useQuery(contractAliasQuery(kg))

export const promotionsQuery = (kg: string) => ({
  queryKey: aliasQueryKeys.promotions(kg),
  queryFn: () => api<Promotion[]>(kgPath(kg) + '/promotions'),
})
export const usePromotions = (kg: string) => useQuery(promotionsQuery(kg))

/**
 * Promote: point an Alias (existing or new) at a version (needs `edit`). The server
 * records the signed-in user as the actor and the version's latest Gate result in the
 * Promotion audit; a Gate never blocks it.
 */
export function usePromote(kg: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ alias, version }: { alias: string; version: number }) =>
      api<Alias>(`${kgPath(kg)}/aliases/${encodeURIComponent(alias)}`, 'PUT', { version }),
    onSuccess: () =>
      Promise.all(
        [aliasQueryKeys.aliases(kg), aliasQueryKeys.promotions(kg), knowledgeGraphsQueryKeys.all()].map((queryKey) =>
          queryClient.invalidateQueries({ queryKey }),
        ),
      ),
  })
}
