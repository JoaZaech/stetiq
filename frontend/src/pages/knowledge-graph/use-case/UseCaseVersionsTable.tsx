import { useMemo, useState } from 'react'
import { useNavigate } from 'react-router'
import type { RowSelectionState } from '@tanstack/react-table'
import type { UseCaseVersion } from '@/api/use-cases'
import { kgCompareUrl } from '@/app/knowledge-graph-sections'
import { CompareToolbar } from '@/components/CompareToolbar'
import { DataTable } from '@/components/DataTable'
import { Checkbox } from '@/components/ui/checkbox'
import { createDataTableColumnHelper, useDataTable } from '@/lib/data-table'
import { formatCount, formatDateTime } from '@/lib/format'

interface VersionRow {
  number: number
  createdAt: string
  questions: number
}

const column = createDataTableColumnHelper<VersionRow>()

const columns = column.columns([
  column.display({
    id: 'select',
    header: () => <span className="sr-only">Select</span>,
    cell: ({ row }) => (
      <Checkbox
        aria-label={`Select v${row.original.number}`}
        checked={row.getIsSelected()}
        onCheckedChange={(checked) => row.toggleSelected(checked === true)}
      />
    ),
  }),
  column.accessor('number', {
    header: 'Version',
    cell: ({ getValue }) => <span className="font-medium">v{getValue()}</span>,
  }),
  column.accessor('createdAt', {
    header: 'Created',
    sortFn: 'datetime',
    cell: ({ getValue }) => <time dateTime={getValue()}>{formatDateTime(getValue())}</time>,
  }),
  column.accessor('questions', {
    header: 'Competency Questions',
    cell: ({ getValue }) =>
      formatCount(getValue(), 'Competency Question'),
  }),
])

/** All Use Case Versions, newest first; select two and Compare to see what changed. */
export function UseCaseVersionsTable({ name, versions }: { name: string; versions: UseCaseVersion[] }) {
  const navigate = useNavigate()
  const [rowSelection, setRowSelection] = useState<RowSelectionState>({})
  const data = useMemo(
    () =>
      versions.map(
        (v): VersionRow => ({
          number: v.number,
          createdAt: v.created_at,
          questions: v.use_case.competency_questions.length,
        }),
      ),
    [versions],
  )
  const table = useDataTable({
    data,
    columns,
    getRowId: (row) => String(row.number),
    state: { rowSelection },
    onRowSelectionChange: setRowSelection,
    initialState: { sorting: [{ id: 'number', desc: true }] },
  })
  const selected = Object.keys(rowSelection)
    .map(Number)
    .sort((a, b) => a - b)

  return (
    <div className="space-y-3">
      <CompareToolbar
        selected={selected.length}
        needs="two"
        noun="versions"
        readyHint="What changed from the older to the newer Use Case Version"
        onCompare={() => navigate(kgCompareUrl(name, 'use-case', selected))}
      />
      <DataTable table={table} label="Use Case Versions" empty="No Use Case Versions yet." />
    </div>
  )
}
