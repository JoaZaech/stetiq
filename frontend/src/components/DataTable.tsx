import type { ReactNode } from 'react'
import { ArrowDown, ArrowUp, ArrowUpDown } from 'lucide-react'
import type { Header, ReactTable, RowData } from '@tanstack/react-table'
import { Button } from '@/components/ui/button'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import type { DataTableFeatures } from '@/lib/data-table'

interface DataTableProps<TData extends RowData> {
  /** A table from `useDataTable` (`@/lib/data-table`). */
  table: ReactTable<DataTableFeatures, TData>
  /** Shown in a single row when no row is left (e.g. after filtering). */
  empty: ReactNode
}

/**
 * Renders any `useDataTable` table as a dense shadcn table: visible columns only,
 * sortable headers become buttons, and a message row when there is nothing to show.
 */
export function DataTable<TData extends RowData>({ table, empty }: DataTableProps<TData>) {
  const rows = table.getRowModel().rows
  return (
    <Table>
      <TableHeader>
        {table.getHeaderGroups().map((group) => (
          <TableRow key={group.id}>
            {group.headers.map((header) => (
              <TableHead key={header.id} aria-sort={ariaSort(header)}>
                {header.isPlaceholder ? null : <HeaderLabel header={header} table={table} />}
              </TableHead>
            ))}
          </TableRow>
        ))}
      </TableHeader>
      <TableBody>
        {rows.length === 0 ? (
          <TableRow>
            <TableCell
              colSpan={table.getVisibleLeafColumns().length}
              className="h-20 text-center text-muted-foreground"
            >
              {empty}
            </TableCell>
          </TableRow>
        ) : (
          rows.map((row) => (
            <TableRow key={row.id} data-state={row.getIsSelected() ? 'selected' : undefined}>
              {row.getVisibleCells().map((cell) => (
                <TableCell key={cell.id}>
                  <table.FlexRender cell={cell} />
                </TableCell>
              ))}
            </TableRow>
          ))
        )}
      </TableBody>
    </Table>
  )
}

function HeaderLabel<TData extends RowData>({
  header,
  table,
}: {
  header: Header<DataTableFeatures, TData, unknown>
  table: ReactTable<DataTableFeatures, TData>
}) {
  const label = <table.FlexRender header={header} />
  if (!header.column.getCanSort()) return label
  const sorted = header.column.getIsSorted()
  const Icon = sorted === 'asc' ? ArrowUp : sorted === 'desc' ? ArrowDown : ArrowUpDown
  return (
    <Button
      variant="ghost"
      size="sm"
      className="-ml-2 h-7 px-2"
      onClick={header.column.getToggleSortingHandler()}
    >
      {label}
      <Icon aria-hidden className="size-3.5 text-muted-foreground" />
    </Button>
  )
}

function ariaSort<TData extends RowData>(header: Header<DataTableFeatures, TData, unknown>) {
  const sorted = header.column.getIsSorted()
  return sorted === 'asc' ? 'ascending' : sorted === 'desc' ? 'descending' : undefined
}
