import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, kgPath } from './client'
import { ontologyVersionQueryKeys } from './ontology-versions'

/** A Competency Question as use_case/format.py `to_dict` sends it: unset fields are omitted. */
export interface CompetencyQuestion {
  /** Stable across Use Case Versions: changing it is a removal plus an addition. */
  id: string
  question: string
  /** Cypher. */
  query?: string
  /** Any JSON value the executed query's rows must match. */
  expected_answer?: unknown
  /** Concept mapping, in Concept-reference syntax: `Customer`, `Ticket.opened_at`, ... */
  concepts?: string[]
}

export interface UseCase {
  description?: string
  /** Sorted by id. */
  competency_questions: CompetencyQuestion[]
}

/** wire.use_case_version_to_json */
export interface UseCaseVersion {
  knowledge_graph: string
  number: number
  content_hash: string
  created_at: string
  use_case: UseCase
}

export const kgUseCaseVersionsPath = (kg: string) => kgPath(kg) + '/use-case-versions'

/** Query keys of a Knowledge Graph's Use Case Versions. */
export const useCaseQueryKeys = {
  all: (kg: string) => ['use-case-versions', kg] as const,
}

/** Oldest first, as the server returns them. */
export const listUseCaseVersionsQuery = (kg: string) => ({
  queryKey: useCaseQueryKeys.all(kg),
  queryFn: () => api<UseCaseVersion[]>(kgUseCaseVersionsPath(kg)),
})
export const useUseCaseVersions = (kg: string) => useQuery(listUseCaseVersionsQuery(kg))

/** What saving an edited Use Case did. */
export interface SavedUseCase {
  /** The Use Case Version holding the saved content: new, or an existing one with the same content. */
  version: UseCaseVersion
  /** False when the content was already registered: the server dedupes by content hash. */
  created: boolean
  /** The latest Use Case Version's number after saving. */
  latest: number
}

/**
 * Register a complete, edited Use Case as a new Use Case Version (needs `edit`). The
 * server re-validates it and returns the existing version for unchanged content.
 *
 * The server judges the latest Ontology Version's structural answerability against a
 * new version as it registers it, so this only refreshes what the page reads.
 */
export function useSaveUseCase(kg: string, onSaved: (saved: SavedUseCase) => void) {
  const queryClient = useQueryClient()
  return useMutation({
    // Here rather than in `mutate()`'s callbacks: those are skipped once the caller
    // unmounts, as a removed question's row (and its dialog) does on the refetch.
    onSuccess: onSaved,
    mutationFn: async (useCase: UseCase): Promise<SavedUseCase> => {
      const before = await queryClient.fetchQuery(listUseCaseVersionsQuery(kg))
      const previous = before.at(-1)?.number ?? 0
      const version = await api<UseCaseVersion>(kgUseCaseVersionsPath(kg), 'POST', {
        use_case: useCase,
      })
      const created = version.number > previous
      return { version, created, latest: created ? version.number : previous }
    },
    onSettled: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: useCaseQueryKeys.all(kg) }),
        queryClient.invalidateQueries({ queryKey: ontologyVersionQueryKeys.all(kg) }),
      ])
    },
  })
}
