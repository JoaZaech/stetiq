import { useMemo, type ReactNode } from 'react'
import { ArrowDown, ArrowUp, ChevronLeft, ChevronRight } from 'lucide-react'
import { useSearchParams } from 'react-router'
import type { UseCaseVersion } from '@/api/use-cases'
import { ErrorAlert } from '@/components/ErrorAlert'
import { FilterMenu } from '@/components/FilterMenu'
import { KpiTiles, type KpiTile } from '@/components/KpiTiles'
import { ListCount, ListToolbar } from '@/components/ListToolbar'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'
import { setOrDeleteParam } from '@/lib/search-params'
import { SEARCH_PARAM } from '@/lib/search'
import { NOT_APPLICABLE, ratioKpi } from '../evaluation/evaluation-kpis'
import { AnswerabilityLabel } from './AnswerabilityLabel'
import { ANSWERABILITY_LABELS, type AnswerabilityStatus } from './answerability'
import {
  catalogRows,
  catalogView,
  formatCatalogSort,
  NO_TASK,
  parseCatalogSort,
  parseStatusFilter,
  STATUS_FILTERS,
  statusCounts,
  taskOptions,
  type CatalogRow,
  type CatalogSortKey,
  type StatusFilter,
} from './catalog'
import { useLatestAnswerability, type LatestAnswerability } from './latest-answerability'

const STATUS_PARAM = 'status'
const TASK_PARAM = 'task'
const SORT_PARAM = 'sort'
const PAGE_PARAM = 'page'

const statusFilterLabel = (status: StatusFilter) => (status === 'all' ? 'All' : ANSWERABILITY_LABELS[status].label)

/**
 * The Questions tab: KPI tiles, then the catalog of the latest Use Case Version's
 * Competency Questions with search, a status and a Task filter, sortable columns and
 * pages of 50. Search, filters, sort and page live in the URL. A row opens the
 * question's sheet, which holds everything else (id, Cypher, mapping, Tasks).
 */
export function QuestionCatalog({
  knowledgeGraph,
  version,
  onOpen,
  addQuestion,
}: {
  knowledgeGraph: string
  version: UseCaseVersion
  onOpen: (id: string) => void
  /** The Add Competency Question button, on the toolbar's right. */
  addQuestion: ReactNode
}) {
  const latest = useLatestAnswerability(knowledgeGraph, version.number)
  const [params, setParams] = useSearchParams()
  const status = useMemo(
    () =>
      latest.state === 'judged' ? new Map<string, AnswerabilityStatus>(latest.answerability.rows.map((r) => [r.id, r.status])) : null,
    [latest],
  )
  const rows = useMemo(() => catalogRows(version.use_case, status), [version.use_case, status])

  const filters = {
    query: params.get(SEARCH_PARAM) ?? '',
    status: parseStatusFilter(params.get(STATUS_PARAM)),
    task: params.get(TASK_PARAM) ?? '',
  }
  const sort = parseCatalogSort(params.get(SORT_PARAM))
  const view = catalogView(rows, filters, sort, Number(params.get(PAGE_PARAM) ?? 1))
  const counts = statusCounts(rows)

  // Any change but paging goes back to the first page.
  const set = (name: string, value: string | null) =>
    setParams(
      (p) => {
        setOrDeleteParam(p, name, value)
        if (name !== PAGE_PARAM) p.delete(PAGE_PARAM)
        return p
      },
      { replace: true },
    )
  const toggleSort = (key: CatalogSortKey) =>
    set(SORT_PARAM, formatCatalogSort({ key, desc: sort.key === key ? !sort.desc : false }))

  if (latest.state === 'error') return <ErrorAlert error={latest.error} />
  return (
    <div className="space-y-4">
      {latest.state === 'pending' ? <Skeleton className="h-20 w-full" /> : <KpiTiles label="Competency Questions" tiles={catalogKpis(latest, rows, counts)} />}
      <ListToolbar
        search={filters.query}
        onSearch={(q) => set(SEARCH_PARAM, q)}
        searchLabel="Search questions"
        actions={addQuestion}
      >
        {status && (
          <ToggleGroup
            type="single"
            variant="outline"
            size="sm"
            aria-label="Status"
            value={filters.status}
            onValueChange={(value) => value && set(STATUS_PARAM, value === 'all' ? null : value)}
          >
            {STATUS_FILTERS.map((s) => (
              <ToggleGroupItem key={s} value={s}>
                {statusFilterLabel(s)} <span className="text-muted-foreground tabular-nums">{counts[s]}</span>
              </ToggleGroupItem>
            ))}
          </ToggleGroup>
        )}
        <FilterMenu label="Task" value={filters.task} options={taskOptions(rows)} onChange={(t) => set(TASK_PARAM, t)} />
      </ListToolbar>
      {rows.length === 0 ? (
        <p className="text-sm text-muted-foreground">No Competency Questions yet.</p>
      ) : (
        <>
          <Table aria-label="Competency Questions">
            <TableHeader>
              <TableRow>
                <SortHead label="Question" sortKey="question" sort={sort} onSort={toggleSort} />
                <SortHead label="Tasks" sortKey="tasks" sort={sort} onSort={toggleSort} className="w-48" />
                <SortHead label="Status" sortKey="status" sort={sort} onSort={toggleSort} className="w-40" />
              </TableRow>
            </TableHeader>
            <TableBody>
              {view.rows.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={3} className="text-muted-foreground">
                    No question matches these filters.
                  </TableCell>
                </TableRow>
              ) : (
                view.rows.map((row) => <QuestionRow key={row.id} row={row} onOpen={onOpen} />)
              )}
            </TableBody>
          </Table>
          <div className="flex flex-wrap items-center justify-between gap-2">
            <ListCount shown={view.shown} total={rows.length} noun="questions" />
            {view.pageCount > 1 && (
              <Pager page={view.page} pageCount={view.pageCount} onPage={(p) => set(PAGE_PARAM, p === 1 ? null : String(p))} />
            )}
          </div>
        </>
      )}
    </div>
  )
}

/** CQ coverage, and how many are unanswerable, can't be checked, and serve no Task. */
function catalogKpis(latest: LatestAnswerability, rows: readonly CatalogRow[], counts: Record<StatusFilter, number>): KpiTile[] {
  const noTask = rows.filter((r) => r.tasks.length === 0).length
  const tasks: KpiTile = { label: 'Not used by any Task', value: String(noTask), tone: noTask === 0 ? 'success' : 'neutral' }
  if (latest.state !== 'judged') {
    const hint = latest.state === 'no-ontology' ? 'No Ontology Version yet' : latest.state === 'not-judged' ? `v${latest.ontologyVersion} not judged yet` : undefined
    return [
      { label: 'CQ coverage', value: NOT_APPLICABLE, hint },
      { label: 'Unanswerable', value: NOT_APPLICABLE },
      { label: "Can't check", value: NOT_APPLICABLE },
      tasks,
    ]
  }
  const coverage = ratioKpi('CQ coverage', { count: latest.answerability.answerable, total: latest.answerability.questions }, `on Ontology Version v${latest.ontologyVersion}`)
  return [
    coverage,
    { label: 'Unanswerable', value: String(counts.unanswerable), tone: counts.unanswerable === 0 ? 'success' : 'failure' },
    { label: "Can't check", value: String(counts.unmapped), tone: counts.unmapped === 0 ? 'success' : 'neutral' },
    tasks,
  ]
}

function QuestionRow({ row, onOpen }: { row: CatalogRow; onOpen: (id: string) => void }) {
  return (
    <TableRow className="cursor-pointer" onClick={() => onOpen(row.id)}>
      <TableCell className="whitespace-normal">
        <button
          type="button"
          onClick={(e) => {
            e.stopPropagation()
            onOpen(row.id)
          }}
          className="text-left hover:underline focus-visible:underline focus-visible:outline-none"
        >
          {row.question}
        </button>
      </TableCell>
      <TableCell>
        <TaskList tasks={row.tasks} />
      </TableCell>
      <TableCell>{row.status ? <AnswerabilityLabel status={row.status} /> : <span className="text-muted-foreground">—</span>}</TableCell>
    </TableRow>
  )
}

/** `review, plan`, or `review +2`; "None" when no Task needs the question. */
function TaskList({ tasks }: { tasks: string[] }) {
  if (tasks.length === 0) return <span className="text-muted-foreground">{NO_TASK}</span>
  const shown = tasks.slice(0, 2)
  return (
    <span className="font-mono text-xs" title={tasks.join(', ')}>
      {shown.join(', ')}
      {tasks.length > shown.length && <span className="text-muted-foreground"> +{tasks.length - shown.length}</span>}
    </span>
  )
}

function SortHead({
  label,
  sortKey,
  sort,
  onSort,
  className,
}: {
  label: string
  sortKey: CatalogSortKey
  sort: { key: CatalogSortKey; desc: boolean }
  onSort: (key: CatalogSortKey) => void
  className?: string
}) {
  const active = sort.key === sortKey
  const Arrow = sort.desc ? ArrowDown : ArrowUp
  return (
    <TableHead className={className} aria-sort={active ? (sort.desc ? 'descending' : 'ascending') : 'none'}>
      <button type="button" onClick={() => onSort(sortKey)} className="inline-flex items-center gap-1 hover:text-foreground">
        {label}
        {active && <Arrow aria-hidden className="size-3.5" />}
      </button>
    </TableHead>
  )
}

function Pager({ page, pageCount, onPage }: { page: number; pageCount: number; onPage: (page: number) => void }) {
  return (
    <nav aria-label="Pages" className="flex items-center gap-2 text-xs text-muted-foreground">
      <Button variant="outline" size="icon" className="size-7" aria-label="Previous page" disabled={page <= 1} onClick={() => onPage(page - 1)}>
        <ChevronLeft aria-hidden />
      </Button>
      <span className="tabular-nums">
        Page {page} of {pageCount}
      </span>
      <Button variant="outline" size="icon" className="size-7" aria-label="Next page" disabled={page >= pageCount} onClick={() => onPage(page + 1)}>
        <ChevronRight aria-hidden />
      </Button>
    </nav>
  )
}
