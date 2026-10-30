import { Fragment, useEffect, useRef } from 'react'
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
import { formatCount } from '@/lib/format'
import type { AttributeGridRow } from './attribute-rows'
import { attributeGroupId } from './table-links'
import { ConceptLink, ShowOnMap } from './TableLinks'

const column = createDataTableColumnHelper<AttributeGridRow>()

const columns = column.columns([
  column.accessor('owner', {
    header: 'Owner',
    ...filterColumn('text'),
    cell: ({ row }) => (
      <span className="font-medium">
        <ConceptLink concept={{ kind: row.original.ownerKind, label: row.original.owner }} />
      </span>
    ),
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
          <span className="ml-2 text-xs text-muted-foreground">
            from <ConceptLink concept={{ kind: 'class', label: row.original.inheritedFrom }} />
          </span>
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
    cell: ({ getValue }) => {
      const from = getValue()
      return from === undefined ? null : <ConceptLink concept={{ kind: 'class', label: from }} />
    },
  }),
  column.accessor('description', {
    header: 'Description',
    ...filterColumn('text'),
    enableSorting: false,
    cell: ({ getValue }) => <span className="text-muted-foreground">{getValue()}</span>,
  }),
  // An attribute is shown on the Map as its owner.
  column.display({
    id: 'map',
    header: '',
    cell: ({ row }) => <ShowOnMap concept={{ kind: row.original.ownerKind, label: row.original.owner }} />,
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

/**
 * A group's header: the owner (a link) with its kind and superclass (a link), or the type,
 * and how many attributes it holds.
 */
function groupHeader(row: Row<DataTableFeatures, AttributeGridRow>) {
  const leaves = row.getLeafRows()
  const first = leaves[0]?.original
  if (row.groupingColumnId === 'owner' && first) {
    const parts = [
      <ConceptLink concept={{ kind: first.ownerKind, label: first.owner }} />,
      first.ownerKind,
      ...(first.ownerParent === undefined
        ? []
        : [
            <>
              subclass of <ConceptLink concept={{ kind: 'class', label: first.ownerParent }} />
            </>,
          ]),
      formatCount(leaves.length, 'attribute'),
    ]
    return parts.map((part, i) => (
      <Fragment key={i}>
        {i > 0 && ' · '}
        {part}
      </Fragment>
    ))
  }
  return `${String(row.groupingValue)} · ${formatCount(leaves.length, 'attribute')}`
}

/** A request to scroll to `owner`'s group; `seq` tells a repeated request from the last. */
export type GroupRequest = { owner: string; seq: number }

/**
 * The Ontology Table's Attributes section: every attribute of every class and relation,
 * grouped. A `reveal` request groups it by owner and scrolls to that owner's group, open.
 */
export function AttributesGrid({
  attributes,
  reveal,
}: {
  attributes: AttributeGridRow[]
  reveal?: GroupRequest | null
}) {
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
  // Grouping by owner goes through the URL, so a request may take a render to be met.
  const revealed = useRef<number | null>(null)
  useEffect(() => {
    if (!reveal || revealed.current === reveal.seq) return
    if (groupedBy !== 'owner') return table.setGrouping(['owner'])
    const group = table.getGroupedRowModel().rows.find((r) => r.groupingValue === reveal.owner)
    if (!group) return
    revealed.current = reveal.seq
    table.setExpanded((expanded) => (expanded === true ? true : { ...expanded, [group.id]: true }))
    document.getElementById(attributeGroupId(reveal.owner))?.scrollIntoView({ block: 'center' })
  }, [reveal, groupedBy, table])
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
      <DataTable
        table={table}
        label="Attributes"
        empty="No attributes match."
        groupHeader={groupHeader}
        rowProps={(row) =>
          row.getIsGrouped() && row.groupingColumnId === 'owner' ? { id: attributeGroupId(String(row.groupingValue)) } : {}
        }
      />
    </>
  )
}
