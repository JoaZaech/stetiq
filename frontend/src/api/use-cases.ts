import { useQuery } from '@tanstack/react-query'
import { api, kgPath } from './client'

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
