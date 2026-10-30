import type { Row } from '@tanstack/react-table'
import { ColumnPicker } from '@/components/ColumnPicker'
import { DataTable, DataTableRowCount } from '@/components/DataTable'
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'
import {
  createDataTableColumnHelper,
  type DataTableFeatures,
  filterColumn,
  useDataTable,
} from '@/lib/data-table'
import { type DataTableParamsOptions, useDataTableParams } from '@/lib/data-table-params'
import type { AttributeGridRow } from './attribute-rows'

const column = createDataTableColumnHelper<AttributeGridRow>()

const columns = column.columns([
  column.accessor('owner', {
    header: 'Owner',
    ...filterColumn('text'),
    cell: ({ getValue }) => <span className="font-medium">{getValue()}</span>,
  }),
  column.accessor('ownerKind', {
    header: 'Owner kind',
    ...filterColumn('values'),
    enableGlobalFilter: false,
  }),
  column.accessor('name', {
    header: 'Attribute',
    ...filterColumn('text'),
    cell: ({ row }) => (
      <span>
        {row.original.name}
        {row.original.inheritedFrom !== undefined && (
          <span className="ml-2 text-xs text-muted-foreground">from {row.original.inheritedFrom}</span>
        )}
      </span>
    ),
  }),
  column.accessor('type', {
    header: 'Type',
    ...filterColumn('values'),
    enableGlobalFilter: false,
    cell: ({ getValue }) => <span className="font-mono text-xs">{getValue()}</span>,
  }),
  column.accessor('required', {
    header: 'Required',
    ...filterColumn('toggle'),
    enableGlobalFilter: false,
    cell: ({ getValue }) => (getValue() ? 'Required' : ''),
  }),
  column.accessor('unique', {
    header: 'Unique',
    ...filterColumn('toggle'),
    enableGlobalFilter: false,
    cell: ({ getValue }) => (getValue() ? 'Unique' : ''),
  }),
  column.accessor('inheritedFrom', {
    header: 'Inherited from',
    ...filterColumn('values'),
    enableGlobalFilter: false,
    sortUndefined: 'last',
  }),
  column.accessor('description', {
    header: 'Description',
    ...filterColumn('text'),
    enableSorting: false,
    cell: ({ getValue }) => <span className="text-muted-foreground">{getValue()}</span>,
  }),
])

/**
 * The Attributes grid's URL state, grouped by owner unless `attributes.group` says
 * otherwise. The search is the Concept search (`?q=`), matching an attribute's owner,
 * name or description.
 */
const ATTRIBUTES_GRID: DataTableParamsOptions = {
  key: 'attributes',
  filters: {
    owner: 'text',
    ownerKind: 'values',
    name: 'text',
    type: 'values',
    required: 'toggle',
    unique: 'toggle',
    inheritedFrom: 'values',
    description: 'text',
  },
  optional: ['ownerKind', 'inheritedFrom'],
  search: 'q',
  grouping: ['owner', 'type'],
}

const GROUP_BY = [
  { value: 'owner', label: 'Owner' },
  { value: 'type', label: 'Type' },
  { value: 'none', label: 'None' },
] as const

const count = (n: number) => `${n} ${n === 1 ? 'attribute' : 'attributes'}`

/** A group's header: the owner with its kind and superclass, or the type, and how many attributes it holds. */
function groupHeader(row: Row<DataTableFeatures, AttributeGridRow>) {
  const leaves = row.getLeafRows()
  const first = leaves[0]?.original
  if (row.groupingColumnId === 'owner' && first) {
    const parent = first.ownerParent === undefined ? [] : [`subclass of ${first.ownerParent}`]
    return [first.owner, first.ownerKind, ...parent, count(leaves.length)].join(' · ')
  }
  return `${String(row.groupingValue)} · ${count(leaves.length)}`
}

/** The Ontology Table's Attributes section: every attribute of every class and relation, grouped. */
export function AttributesGrid({ attributes }: { attributes: AttributeGridRow[] }) {
  const grid = useDataTableParams(ATTRIBUTES_GRID)
  const table = useDataTable({
    data: attributes,
    columns,
    getRowId: (row) => row.id,
    globalFilterFn: 'includesString',
    groupedColumnMode: false,
    initialState: { expanded: true },
    ...grid.tableOptions,
  })
  const [groupedBy = 'none'] = table.store.state.grouping
  return (
    <>
      <div className="flex items-center justify-between gap-4">
        <DataTableRowCount table={table} noun="attributes" />
        <div className="flex items-center gap-2">
          <span className="text-xs text-muted-foreground">Group by</span>
          <ToggleGroup
            type="single"
            variant="outline"
            size="sm"
            spacing={0}
            aria-label="Group attributes by"
            value={groupedBy}
            // Radix sends '' when the active item is clicked again: keep the current grouping.
            onValueChange={(value) => value && table.setGrouping(value === 'none' ? [] : [value])}
          >
            {GROUP_BY.map(({ value, label }) => (
              <ToggleGroupItem key={value} value={value}>
                {label}
              </ToggleGroupItem>
            ))}
          </ToggleGroup>
          <ColumnPicker
            groups={[
              {
                label: 'Columns',
                columns: [
                  { id: 'ownerKind', label: 'Owner kind' },
                  { id: 'inheritedFrom', label: 'Inherited from' },
                ],
              },
            ]}
            visible={grid.shown}
            onToggle={grid.setShown}
          />
        </div>
      </div>
      <DataTable table={table} label="Attributes" empty="No attributes match." groupHeader={groupHeader} />
    </>
  )
}
