import { useQuery } from '@tanstack/react-query'
import { api } from './client'

export type Permission = 'read' | 'edit'

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
