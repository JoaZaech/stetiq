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
 * (e.g. a search box), column visibility (column choosers) and row selection (Compare).
 */
import {
  columnFilteringFeature,
  columnVisibilityFeature,
  createFilteredRowModel,
  createSortedRowModel,
  createTableHook,
  filterFn_includesString,
  globalFilteringFeature,
  rowSelectionFeature,
  rowSortingFeature,
  sortFn_alphanumeric,
  sortFn_basic,
  sortFn_datetime,
  sortFn_text,
  tableFeatures,
} from '@tanstack/react-table'

export const dataTableFeatures = tableFeatures({
  columnFilteringFeature,
  globalFilteringFeature,
  filteredRowModel: createFilteredRowModel(),
  filterFns: { includesString: filterFn_includesString },
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
})

export type DataTableFeatures = typeof dataTableFeatures

export const {
  createAppColumnHelper: createDataTableColumnHelper,
  useAppTable: useDataTable,
} = createTableHook({ features: dataTableFeatures })
