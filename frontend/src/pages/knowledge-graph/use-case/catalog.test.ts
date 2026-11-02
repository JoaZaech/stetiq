import { describe, expect, it } from 'vitest'
import type { UseCase } from '@/api/use-cases'
import type { AnswerabilityStatus } from './answerability'
import {
  catalogRows,
  catalogView,
  CATALOG_PAGE_SIZE,
  filterCatalog,
  formatCatalogSort,
  NO_TASK,
  parseCatalogSort,
  parseStatusFilter,
  sortCatalog,
  statusCounts,
  taskOptions,
} from './catalog'

const useCase: UseCase = {
  competency_questions: [
    { id: 'a', question: 'Who handled each breakdown?' },
    { id: 'b', question: 'Which suppliers do we depend on?' },
    { id: 'c', question: 'Which faults keep coming back?' },
  ],
  consumers: [
    {
      id: 'lead',
      name: 'Maintenance lead',
      tasks: [
        { id: 'review', description: '', competency_questions: ['a', 'c'] },
        { id: 'plan', description: '', competency_questions: ['a'] },
      ],
    },
  ],
}

const status = new Map<string, AnswerabilityStatus>([
  ['a', 'unanswerable'],
  ['b', 'answerable'],
])

describe('catalogRows', () => {
  it('gives each question its Tasks and status; unjudged questions are unmapped', () => {
    expect(catalogRows(useCase, status)).toEqual([
      { id: 'a', question: 'Who handled each breakdown?', tasks: ['review', 'plan'], status: 'unanswerable' },
      { id: 'b', question: 'Which suppliers do we depend on?', tasks: [], status: 'answerable' },
      { id: 'c', question: 'Which faults keep coming back?', tasks: ['review'], status: 'unmapped' },
    ])
  })

  it('has no status at all while the Ontology Version is not judged', () => {
    expect(catalogRows(useCase, null).map((r) => r.status)).toEqual([null, null, null])
  })
})

describe('filtering', () => {
  const rows = catalogRows(useCase, status)

  it('filters by status, Task and search', () => {
    expect(filterCatalog(rows, { query: '', status: 'unanswerable', task: '' }).map((r) => r.id)).toEqual(['a'])
    expect(filterCatalog(rows, { query: '', status: 'all', task: NO_TASK }).map((r) => r.id)).toEqual(['b'])
    expect(filterCatalog(rows, { query: '', status: 'all', task: 'review' }).map((r) => r.id)).toEqual(['a', 'c'])
    expect(filterCatalog(rows, { query: 'which', status: 'all', task: '' }).map((r) => r.id)).toEqual(['b', 'c'])
    expect(filterCatalog(rows, { query: 'faults', status: 'all', task: 'plan' })).toEqual([])
  })

  it('counts each status and each Task', () => {
    expect(statusCounts(rows)).toEqual({ all: 3, answerable: 1, unanswerable: 1, unmapped: 1 })
    expect(taskOptions(rows)).toEqual([
      [NO_TASK, 1],
      ['plan', 1],
      ['review', 2],
    ])
  })
})

describe('sorting', () => {
  const rows = catalogRows(useCase, status)

  it('sorts by question, Tasks or status, worst status first', () => {
    expect(sortCatalog(rows, { key: 'question', desc: false }).map((r) => r.id)).toEqual(['c', 'b', 'a'])
    expect(sortCatalog(rows, { key: 'status', desc: false }).map((r) => r.id)).toEqual(['a', 'c', 'b'])
    expect(sortCatalog(rows, { key: 'tasks', desc: true }).map((r) => r.id)).toEqual(['a', 'c', 'b'])
  })

  it('round-trips the sort through its URL param, the default leaving it clean', () => {
    expect(formatCatalogSort({ key: 'question', desc: false })).toBeNull()
    expect(parseCatalogSort(formatCatalogSort({ key: 'status', desc: true }))).toEqual({ key: 'status', desc: true })
    expect(parseCatalogSort('nonsense')).toEqual({ key: 'question', desc: false })
    expect(parseStatusFilter('bogus')).toBe('all')
  })
})

describe('catalogView', () => {
  it('pages the filtered rows', () => {
    const many: UseCase = {
      competency_questions: Array.from({ length: 120 }, (_, i) => ({ id: `q${String(i).padStart(3, '0')}`, question: `Q ${i}` })),
    }
    const rows = catalogRows(many, null)
    const view = catalogView(rows, { query: '', status: 'all', task: '' }, { key: 'question', desc: false }, 3)
    expect(view).toMatchObject({ shown: 120, page: 3, pageCount: 3 })
    expect(view.rows).toHaveLength(120 - 2 * CATALOG_PAGE_SIZE)
  })
})
