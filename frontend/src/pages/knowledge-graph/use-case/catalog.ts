import type { UseCase } from '@/api/use-cases'
import { matchesSearch, pageOf } from '@/lib/search'
import type { AnswerabilityStatus } from './answerability'

/**
 * The question catalog of the Use Case page: every Competency Question of the latest Use
 * Case Version as a row, searched, filtered by status and Task, sorted and paged. It
 * scales to hundreds of questions, where the old list did not.
 */
export interface CatalogRow {
  id: string
  question: string
  /** Ids of the Tasks that need it, in Consumer order. */
  tasks: string[]
  /** Its answerability on the latest Ontology Version; null while not judged. */
  status: AnswerabilityStatus | null
}

/** Rows per page. */
export const CATALOG_PAGE_SIZE = 50

export const STATUS_FILTERS = ['all', 'answerable', 'unanswerable', 'unmapped'] as const
export type StatusFilter = (typeof STATUS_FILTERS)[number]

/** The Task filter's value for questions no Task needs; `''` is all, else a Task id. */
export const NO_TASK = 'No Task'

export const CATALOG_SORTS = ['question', 'tasks', 'status'] as const
export type CatalogSortKey = (typeof CATALOG_SORTS)[number]
export interface CatalogSort {
  key: CatalogSortKey
  desc: boolean
}

export interface CatalogFilters {
  query: string
  status: StatusFilter
  task: string
}

export function catalogRows(useCase: UseCase, status: ReadonlyMap<string, AnswerabilityStatus> | null): CatalogRow[] {
  const tasksOf = new Map<string, string[]>()
  for (const consumer of useCase.consumers ?? []) {
    for (const task of consumer.tasks ?? []) {
      for (const id of task.competency_questions ?? []) tasksOf.set(id, [...(tasksOf.get(id) ?? []), task.id])
    }
  }
  return useCase.competency_questions.map((q) => ({
    id: q.id,
    question: q.question,
    tasks: tasksOf.get(q.id) ?? [],
    status: status?.get(q.id) ?? (status ? 'unmapped' : null),
  }))
}

/** Rows matching the search (question text and id), the status and the Task filter. */
export function filterCatalog(rows: readonly CatalogRow[], { query, status, task }: CatalogFilters): CatalogRow[] {
  return rows.filter(
    (r) =>
      (status === 'all' || r.status === status) &&
      (task === '' || (task === NO_TASK ? r.tasks.length === 0 : r.tasks.includes(task))) &&
      matchesSearch(query, [r.question, r.id]),
  )
}

/** How many rows hold each status, and all of them: the status filter's counts. */
export function statusCounts(rows: readonly CatalogRow[]): Record<StatusFilter, number> {
  const counts: Record<StatusFilter, number> = { all: rows.length, answerable: 0, unanswerable: 0, unmapped: 0 }
  for (const row of rows) if (row.status) counts[row.status] += 1
  return counts
}

/** The Task filter's options: questions no Task needs, then each Task, with counts. */
export function taskOptions(rows: readonly CatalogRow[]): [string, number][] {
  const counts = new Map<string, number>()
  for (const row of rows) for (const task of row.tasks) counts.set(task, (counts.get(task) ?? 0) + 1)
  const none = rows.filter((r) => r.tasks.length === 0).length
  return [
    ...(none > 0 ? ([[NO_TASK, none]] as [string, number][]) : []),
    ...[...counts].sort((a, b) => a[0].localeCompare(b[0])),
  ]
}

/** Status sorts worst first: unanswerable, can't check, answerable, then not judged. */
const STATUS_ORDER: Record<AnswerabilityStatus, number> = { unanswerable: 0, unmapped: 1, answerable: 2 }

export function sortCatalog(rows: readonly CatalogRow[], { key, desc }: CatalogSort): CatalogRow[] {
  const compare = (a: CatalogRow, b: CatalogRow): number => {
    switch (key) {
      case 'question':
        return a.question.localeCompare(b.question)
      case 'tasks':
        return a.tasks.length - b.tasks.length
      case 'status':
        return (a.status ? STATUS_ORDER[a.status] : 3) - (b.status ? STATUS_ORDER[b.status] : 3)
    }
  }
  return [...rows].sort((a, b) => (desc ? -compare(a, b) : compare(a, b)) || a.id.localeCompare(b.id))
}

/** `question`, `-status`: a sort as its URL param; `null` (question, ascending) is the default. */
export function parseCatalogSort(value: string | null): CatalogSort {
  const desc = value?.startsWith('-') ?? false
  const key = (value ?? '').replace(/^-/, '')
  return (CATALOG_SORTS as readonly string[]).includes(key)
    ? { key: key as CatalogSortKey, desc }
    : { key: 'question', desc: false }
}

export function formatCatalogSort({ key, desc }: CatalogSort): string | null {
  if (key === 'question' && !desc) return null
  return `${desc ? '-' : ''}${key}`
}

/** The search, filters, sort and page applied: what the table shows. */
export function catalogView(
  rows: readonly CatalogRow[],
  filters: CatalogFilters,
  sort: CatalogSort,
  page: number,
): { shown: number; page: number; pageCount: number; rows: CatalogRow[] } {
  const filtered = sortCatalog(filterCatalog(rows, filters), sort)
  const paged = pageOf(filtered, page, CATALOG_PAGE_SIZE)
  return { shown: filtered.length, page: paged.page, pageCount: paged.pageCount, rows: paged.items }
}

export const parseStatusFilter = (value: string | null): StatusFilter =>
  (STATUS_FILTERS as readonly string[]).includes(value ?? '') ? (value as StatusFilter) : 'all'
