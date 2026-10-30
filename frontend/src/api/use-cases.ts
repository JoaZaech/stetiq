import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, kgPath } from './client'
import { ontologyVersionsQuery } from './ontology-versions'

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

/** Oldest first, as the server returns them. */
export const listUseCaseVersionsQuery = (kg: string) => ({
  queryKey: ['use-case-versions', kg],
  queryFn: () => api<UseCaseVersion[]>(kgUseCaseVersionsPath(kg)),
})
export const useUseCaseVersions = (kg: string) => useQuery(listUseCaseVersionsQuery(kg))

/** What saving an edited Use Case did. */
export interface SavedUseCase {
  /** The Use Case Version holding the saved content: new, or an existing one with the same content. */
  version: UseCaseVersion
  /** False when the content was already registered: the server dedupes by content hash. */
  created: boolean
  /** Why structural answerability could not be judged for the new version, if it could not. */
  evaluationError?: unknown
}

/**
 * Register a complete, edited Use Case as a new Use Case Version (needs `edit`). The
 * server re-validates it and returns the existing version for unchanged content.
 *
 * A new version is then judged for structural answerability against the latest
 * Ontology Version (`POST .../evaluate`), so the page can show the result straight away.
 */
export function useSaveUseCase(kg: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (useCase: UseCase): Promise<SavedUseCase> => {
      const before = await queryClient.fetchQuery(listUseCaseVersionsQuery(kg))
      const latest = before.at(-1)?.number ?? 0
      const version = await api<UseCaseVersion>(kgUseCaseVersionsPath(kg), 'POST', {
        use_case: useCase,
      })
      const created = version.number > latest
      if (!created) return { version, created }
      try {
        const ontology = (await queryClient.fetchQuery(ontologyVersionsQuery(kg))).at(-1)
        if (ontology) {
          await api(`${kgPath(kg)}/ontology-versions/${ontology.number}/evaluate`, 'POST', {
            use_case_version: version.number,
          })
        }
      } catch (evaluationError) {
        return { version, created, evaluationError }
      }
      return { version, created }
    },
    onSettled: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['use-case-versions', kg] }),
        queryClient.invalidateQueries({ queryKey: ['ontology-versions', kg] }),
      ])
    },
  })
}
