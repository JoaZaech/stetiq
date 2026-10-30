import { type ComponentProps, useId, type ReactNode } from 'react'
import { ArrowDown, ArrowUp, ArrowUpDown, ChevronDown, ChevronRight, Filter } from 'lucide-react'
import type { Column, Header, ReactTable, Row, RowData } from '@tanstack/react-table'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { Switch } from '@/components/ui/switch'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { type DataTableFeatures, filterOptions } from '@/lib/data-table'

interface DataTableProps<TData extends RowData> {
  /** A table from `useDataTable` (`@/lib/data-table`). */
  table: ReactTable<DataTableFeatures, TData>
  /** Shown in a single row when no row is left (e.g. after filtering). */
  empty: ReactNode
  /** The table's accessible name, e.g. "Ontology Versions". */
  label?: string
  /** Extra props for a row's `<tr>`, e.g. an `id` to scroll to it. */
  rowProps?: (row: Row<DataTableFeatures, TData>) => ComponentProps<'tr'>
  /**
   * What a group's header row shows when the table is grouped (its `grouping` state):
   * e.g. the grouped value and how many rows it holds. The header spans the row and
   * collapses or expands the group.
   */
  groupHeader?: (row: Row<DataTableFeatures, TData>) => ReactNode
}

/**
 * Renders any `useDataTable` table as a dense shadcn table: visible columns only,
 * sortable headers become buttons, a column with a header filter (`filterColumn`) gets
 * a filter button beside its name, a grouped table gets a collapsible header row per
 * group, and a message row shows when there is nothing to show.
 */
export function DataTable<TData extends RowData>({
  table,
  empty,
  label,
  rowProps,
  groupHeader,
}: DataTableProps<TData>) {
  const rows = table.getRowModel().rows
  const columns = table.getVisibleLeafColumns().length
  return (
    <Table aria-label={label}>
      <TableHeader>
        {table.getHeaderGroups().map((group) => (
          <TableRow key={group.id}>
            {group.headers.map((header) => (
              <TableHead key={header.id} aria-sort={ariaSort(header)}>
                {header.isPlaceholder ? null : (
                  <span className="inline-flex items-center gap-0.5">
                    <HeaderLabel header={header} table={table} />
                    {header.column.columnDef.meta?.filter && <ColumnFilter column={header.column} table={table} />}
                  </span>
                )}
              </TableHead>
            ))}
          </TableRow>
        ))}
      </TableHeader>
      <TableBody>
        {rows.length === 0 ? (
          <TableRow>
            <TableCell
              colSpan={columns}
              className="h-20 text-center text-muted-foreground"
            >
              {empty}
            </TableCell>
          </TableRow>
        ) : (
          rows.map((row) =>
            row.getIsGrouped() ? (
              <GroupHeaderRow key={row.id} row={row} columns={columns}>
                {groupHeader?.(row) ?? String(row.groupingValue)}
              </GroupHeaderRow>
            ) : (
              <TableRow key={row.id} data-state={row.getIsSelected() ? 'selected' : undefined} {...rowProps?.(row)}>
                {row.getVisibleCells().map((cell) => (
                  <TableCell key={cell.id}>
                    <table.FlexRender cell={cell} />
                  </TableCell>
                ))}
              </TableRow>
            ),
          )
        )}
      </TableBody>
    </Table>
  )
}

/** A group's header row: a button spanning the row that collapses or expands the group. */
function GroupHeaderRow<TData extends RowData>({
  row,
  columns,
  children,
}: {
  row: Row<DataTableFeatures, TData>
  columns: number
  children: ReactNode
}) {
  const open = row.getIsExpanded()
  const Chevron = open ? ChevronDown : ChevronRight
  return (
    <TableRow className="bg-muted/50 hover:bg-muted/50">
      <TableCell colSpan={columns} className="py-1">
        <Button
          variant="ghost"
          size="sm"
          className="-ml-2 h-7 px-2 font-normal"
          aria-expanded={open}
          onClick={row.getToggleExpandedHandler()}
        >
          <Chevron aria-hidden className="size-4" />
          {children}
        </Button>
      </TableCell>
    </TableRow>
  )
}

/** How many of a table's rows its filters and search leave, e.g. "12 of 34 classes". */
export function DataTableRowCount<TData extends RowData>({
  table,
  noun,
}: {
  table: ReactTable<DataTableFeatures, TData>
  /** What a row is, plural, e.g. "classes". */
  noun: string
}) {
  const shown = table.getFilteredRowModel().rows.length
  const total = table.getCoreRowModel().rows.length
  return (
    <p className="text-xs text-muted-foreground tabular-nums" aria-live="polite">
      {shown === total ? `${total} ${noun}` : `${shown} of ${total} ${noun}`}
    </p>
  )
}

/** A column's name as text, for labels: its header when that is a string, else its id. */
const columnName = <TData extends RowData>(column: Column<DataTableFeatures, TData, unknown>) =>
  typeof column.columnDef.header === 'string' ? column.columnDef.header : column.id

/**
 * The filter button in a column's header and its popover: a text box, a checkbox per
 * value the column holds, or a switch, by the column's filter kind.
 */
function ColumnFilter<TData extends RowData>({
  column,
  table,
}: {
  column: Column<DataTableFeatures, TData, unknown>
  table: ReactTable<DataTableFeatures, TData>
}) {
  const id = useId()
  const name = columnName(column)
  const value = column.getFilterValue()
  const active = column.getIsFiltered()
  const kind = column.columnDef.meta?.filter
  let control: ReactNode = null
  if (kind === 'text') {
    control = (
      <Input
        id={id}
        aria-label={`Filter ${name}`}
        placeholder="Contains…"
        className="h-8"
        value={typeof value === 'string' ? value : ''}
        onChange={(e) => column.setFilterValue(e.target.value)}
      />
    )
  } else if (kind === 'values') {
    const picked = new Set(Array.isArray(value) ? (value as string[]) : [])
    const options = filterOptions(table.getCoreRowModel().rows.map((r) => r.getValue(column.id)))
    control = (
      <fieldset aria-label={`Filter ${name}`} className="max-h-64 space-y-1.5 overflow-y-auto">
        {options.length === 0 && <p className="text-sm text-muted-foreground">No values</p>}
        {options.map((option) => (
          <Label key={option} className="font-normal">
            <Checkbox
              checked={picked.has(option)}
              onCheckedChange={(checked) =>
                column.setFilterValue(
                  checked === true ? [...picked, option] : [...picked].filter((p) => p !== option),
                )
              }
            />
            {option}
          </Label>
        ))}
      </fieldset>
    )
  } else if (kind === 'toggle') {
    control = (
      <Label className="font-normal">
        <Switch checked={value === true} onCheckedChange={(on) => column.setFilterValue(on ? true : undefined)} />
        Only {name.toLowerCase()}
      </Label>
    )
  }
  return (
    <Popover>
      <PopoverTrigger asChild>
        <Button
          variant="ghost"
          size="icon"
          className="size-6 data-[active=true]:text-primary"
          data-active={active}
          aria-label={active ? `Filter ${name} (on)` : `Filter ${name}`}
        >
          <Filter aria-hidden className={active ? 'size-3.5 fill-current' : 'size-3.5 text-muted-foreground'} />
        </Button>
      </PopoverTrigger>
      <PopoverContent align="start" className="w-60 space-y-2">
        {control}
        {active && (
          <Button variant="ghost" size="sm" className="h-7 px-2" onClick={() => column.setFilterValue(undefined)}>
            Clear filter
          </Button>
        )}
      </PopoverContent>
    </Popover>
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
