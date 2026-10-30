import { useMemo, type ReactNode } from 'react'
import type { CompetencyQuestion } from '@/api/use-cases'
import { DataTable } from '@/components/DataTable'
import { createDataTableColumnHelper, useDataTable } from '@/lib/data-table'
import { FIELD_LABELS } from './compare'
import { ConceptMapping, ExpectedAnswer, Query } from './fields'

const column = createDataTableColumnHelper<CompetencyQuestion>()

const columns = column.columns([
  column.accessor('id', {
    header: 'Id',
    cell: ({ getValue }) => <code className="font-mono text-xs">{getValue()}</code>,
  }),
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
}

/** A Use Case Version's Competency Questions, sorted by id. */
export function CompetencyQuestionsTable({ questions, rowActions }: CompetencyQuestionsTableProps) {
  const allColumns = useMemo(
    () =>
      rowActions
        ? [
            ...columns,
            column.display({
              id: 'actions',
              header: () => <span className="sr-only">Actions</span>,
              cell: ({ row }) => (
                <div className="flex justify-end gap-1">{rowActions(row.original)}</div>
              ),
            }),
          ]
        : columns,
    [rowActions],
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
