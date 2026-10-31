/**
 * The one TanStack Table (v9) setup every list in the app uses, so tables share
 * features and behave alike. Build a table with:
 *
 *   const column = createDataTableColumnHelper<Row>()
 *   const columns = column.columns([column.accessor('name', { header: 'Name' }), ...])  // module scope
 *   const table = useDataTable({ data, columns })   // keep `data` stable (e.g. `query.data ?? NO_ROWS`)
 *   return <DataTable table={table} empty="Nothing yet" />
 *
 * Registered features: sorting (click a header), column filtering + global filtering
 * (e.g. a search box), column visibility (column choosers), row selection (Compare), and
 * grouping by a column with collapsible groups (`DataTable`'s `groupHeader`).
 *
 * A grid (e.g. the Ontology Table's sections) also gives columns a filter in their
 * header with `...filterColumn('text' | 'values' | 'toggle')`, keeps its sort, filters
 * and search in the URL with `useDataTableParams` (`./data-table-params`), and shows
 * `DataTableRowCount` ("12 of 34") next to it.
 */
import {
  columnFilteringFeature,
  columnGroupingFeature,
  columnVisibilityFeature,
  createExpandedRowModel,
  createFilteredRowModel,
  createGroupedRowModel,
  createSortedRowModel,
  createTableHook,
  type FilterFn,
  filterFn_includesString,
  globalFilteringFeature,
  type RowData,
  rowExpandingFeature,
  rowSelectionFeature,
  rowSortingFeature,
  sortFn_alphanumeric,
  sortFn_basic,
  sortFn_datetime,
  sortFn_text,
  tableFeatures,
  type TableFeatures,
} from '@tanstack/react-table'

/**
 * A column's header filter, by the kind of value it filters: `text` (contains, for
 * names and descriptions), `values` (one of the picked values, for type and kind),
 * `toggle` (only rows where it is true, for booleans).
 */
export type ColumnFilterKind = 'text' | 'values' | 'toggle'

export interface DataTableColumnMeta {
  /** Gives the column a header filter of this kind (set by `filterColumn`). */
  filter?: ColumnFilterKind
}

const asList = (value: unknown): unknown[] => (Array.isArray(value) ? value : [value])
const present = (v: unknown) => v !== undefined && v !== null && v !== ''

/**
 * Whether a cell value passes a column filter of `kind`, whose value is the text, the
 * picked values, or `true`. A list value (e.g. a class's outgoing relations) passes when
 * any of its items does.
 */
export function matchesColumnFilter(kind: ColumnFilterKind, value: unknown, filter: unknown): boolean {
  if (kind === 'toggle') return value === true
  const items = asList(value).filter(present)
  if (kind === 'values') {
    const picked = new Set(filter as string[])
    return items.some((v) => picked.has(String(v)))
  }
  const text = String(filter).toLowerCase()
  return items.some((v) => String(v).toLowerCase().includes(text))
}

/** What a `values` filter offers for a column's cell values: each distinct one, sorted. */
export function filterOptions(values: readonly unknown[]): string[] {
  const options = new Set(values.flatMap(asList).filter(present).map(String))
  return [...options].sort((a, b) => a.localeCompare(b))
}

function columnFilterFn(kind: ColumnFilterKind): FilterFn<TableFeatures, RowData> {
  const fn: FilterFn<TableFeatures, RowData> = (row, columnId, filter) =>
    matchesColumnFilter(kind, row.getValue(columnId), filter)
  // An empty text, no picked value or a toggle that is off is no filter at all.
  fn.autoRemove = (filter: unknown) =>
    kind === 'toggle' ? filter !== true : kind === 'values' ? !Array.isArray(filter) || filter.length === 0 : !filter
  return fn
}

export const dataTableFeatures = tableFeatures({
  columnFilteringFeature,
  globalFilteringFeature,
  filteredRowModel: createFilteredRowModel(),
  filterFns: {
    includesString: filterFn_includesString,
    text: columnFilterFn('text'),
    values: columnFilterFn('values'),
    toggle: columnFilterFn('toggle'),
  },
  rowSortingFeature,
  sortedRowModel: createSortedRowModel(),
  sortFns: {
    alphanumeric: sortFn_alphanumeric,
    basic: sortFn_basic,
    datetime: sortFn_datetime,
    text: sortFn_text,
  },
  columnVisibilityFeature,
  rowSelectionFeature,
  columnGroupingFeature,
  groupedRowModel: createGroupedRowModel(),
  rowExpandingFeature,
  expandedRowModel: createExpandedRowModel(),
  columnMeta: {} as DataTableColumnMeta,
})

export type DataTableFeatures = typeof dataTableFeatures

/**
 * The column options that give a column a header filter of `kind`; spread them into a
 * column def: `column.accessor('label', { header: 'Class', ...filterColumn('text') })`.
 */
export const filterColumn = (kind: ColumnFilterKind) => ({ filterFn: kind, meta: { filter: kind } })

export const {
  createAppColumnHelper: createDataTableColumnHelper,
  useAppTable: useDataTable,
} = createTableHook({ features: dataTableFeatures })
