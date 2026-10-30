import { useQuery } from '@tanstack/react-query'
import { api } from './client'

export type Permission = 'read' | 'edit'

/** The grant key meaning every Knowledge Graph, including ones not created yet. */
export const ALL_KNOWLEDGE_GRAPHS = '*'

/** GET /whoami: who the UI acts as. `*` grants every Knowledge Graph. */
export interface WhoAmI {
  /** `local` under `stetiq ui` (no token), `server` under `stetiq server`. */
  mode: 'local' | 'server'
  user: string
  grants: Record<string, Permission>
}

export const whoAmIQuery = {
  queryKey: ['whoami'],
  queryFn: () => api<WhoAmI>('/whoami'),
  staleTime: Infinity,
} as const

export function useWhoAmI() {
  return useQuery(whoAmIQuery)
}

/**
 * Whether `whoami` may edit `knowledgeGraph` (directly or through `*`). Unknown (still
 * loading) means no. This only decides which controls are enabled: the server checks
 * every write itself.
 */
export function canEdit(whoami: WhoAmI | undefined, knowledgeGraph: string): boolean {
  const grants = whoami?.grants ?? {}
  return grants[knowledgeGraph] === 'edit' || grants[ALL_KNOWLEDGE_GRAPHS] === 'edit'
}

/** `canEdit` for the current user. */
export function useCanEdit(knowledgeGraph: string): boolean {
  return canEdit(useWhoAmI().data, knowledgeGraph)
}
