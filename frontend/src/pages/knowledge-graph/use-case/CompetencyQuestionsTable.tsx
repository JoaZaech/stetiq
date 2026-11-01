import { useMemo, type ReactNode } from 'react'
import type { CompetencyQuestion } from '@/api/use-cases'
import { DataTable } from '@/components/DataTable'
import { Badge } from '@/components/ui/badge'
import { createDataTableColumnHelper, useDataTable } from '@/lib/data-table'
import { FIELD_LABELS } from './compare'
import { ConceptMapping, ExpectedAnswer, Query } from './fields'

const column = createDataTableColumnHelper<CompetencyQuestion>()

/** The Id column, marking the questions in `servingNoTask`. */
const idColumns = (servingNoTask?: ReadonlySet<string>) =>
  column.columns([
    column.accessor('id', {
      header: 'Id',
      cell: ({ getValue }) => (
        <span className="flex flex-wrap items-center gap-1.5">
          <code className="font-mono text-xs">{getValue()}</code>
          {servingNoTask?.has(getValue()) && <Badge variant="outline">serves no Task</Badge>}
        </span>
      ),
    }),
  ])

const columns = column.columns([
  column.accessor('question', {
    header: FIELD_LABELS.question,
    cell: ({ getValue }) => <span className="whitespace-normal">{getValue()}</span>,
  }),
  column.display({
    id: 'query',
    header: FIELD_LABELS.query,
    cell: ({ row }) => <Query value={row.original.query} />,
  }),
  column.display({
    id: 'expected_answer',
    header: FIELD_LABELS.expected_answer,
    cell: ({ row }) => <ExpectedAnswer value={row.original.expected_answer} />,
  }),
  column.display({
    id: 'concepts',
    header: FIELD_LABELS.concepts,
    cell: ({ row }) => <ConceptMapping value={row.original.concepts} />,
  }),
])

interface CompetencyQuestionsTableProps {
  questions: CompetencyQuestion[]
  /**
   * Controls at the end of each row, e.g. Edit / Remove (#33). Pass a stable function
   * (module scope or `useCallback`): a new one rebuilds the columns.
   */
  rowActions?: (question: CompetencyQuestion) => ReactNode
  /** Ids of the questions no Consumer's Task needs, marked "serves no Task". Pass a stable set. */
  servingNoTask?: ReadonlySet<string>
}

/** A Use Case Version's Competency Questions, sorted by id. */
export function CompetencyQuestionsTable({
  questions,
  rowActions,
  servingNoTask,
}: CompetencyQuestionsTableProps) {
  const allColumns = useMemo(
    () =>
      rowActions
        ? [
            ...idColumns(servingNoTask),
            ...columns,
            column.display({
              id: 'actions',
              header: () => <span className="sr-only">Actions</span>,
              cell: ({ row }) => (
                <div className="flex justify-end gap-1">{rowActions(row.original)}</div>
              ),
            }),
          ]
        : [...idColumns(servingNoTask), ...columns],
    [rowActions, servingNoTask],
  )
  const table = useDataTable({
    data: questions,
    columns: allColumns,
    getRowId: (q) => q.id,
    initialState: { sorting: [{ id: 'id', desc: false }] },
  })
  return (
    <DataTable
      table={table}
      label="Competency Questions"
      empty="This Use Case Version has no Competency Questions."
    />
  )
}
