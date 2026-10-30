/**
 * URL state of a grid (a `useDataTable` table with header filters), so a link or a reload
 * opens it sorted, filtered and searched the same way. Each table's params carry its
 * `key`, so several grids share a page:
 *
 * - `?<key>.sort=<column id>` (repeated, in order; `-<column id>` sorts descending);
 * - `?<key>.f.<column id>=<value>`: a column filter, repeated for a value list, `1` for a toggle;
 * - `?<key>.q=<text>`: the search, or a param several grids share (`search`, e.g. `q`);
 * - `?<key>.col=<column id>` (repeated): the optional columns shown (see `ColumnPicker`);
 * - `?<key>.group=<column id>`: the column rows are grouped by, `none` for no grouping;
 *   absent, the first of `grouping`.
 *
 * Use it with `useDataTable`:
 *
 *   const grid = useDataTableParams({ key: 'classes', filters: { label: 'text' }, optional: ['deprecated'] })
 *   const table = useDataTable({ data, columns, ...grid.tableOptions })
 *   <ColumnPicker groups={...} visible={grid.shown} onToggle={grid.setShown} />
 */
import { useCallback, useMemo } from 'react'
import { useSearchParams } from 'react-router'
import type {
  ColumnFiltersState,
  ColumnVisibilityState,
  GroupingState,
  SortingState,
  Updater,
} from '@tanstack/react-table'
import type { ColumnFilterKind } from './data-table'

export interface DataTableParamsOptions {
  /** Names this grid's params, e.g. `classes` → `?classes.sort=label`. */
  key: string
  /** The filter kind of each column with a header filter, by column id. */
  filters: Readonly<Record<string, ColumnFilterKind>>
  /** Column ids hidden unless picked in the column picker. */
  optional?: readonly string[]
  /** The search param, when grids share one search box (e.g. `q`); `<key>.q` by default. */
  search?: string
  /** Column ids rows may be grouped by, the default first; no grouping when absent. */
  grouping?: readonly string[]
}

/** The table state kept in the URL. */
export interface DataTableParamsState {
  sorting: SortingState
  columnFilters: ColumnFiltersState
  globalFilter: string
  columnVisibility: ColumnVisibilityState
  /** The column rows are grouped by (at most one); only for a table with `grouping`. */
  grouping?: GroupingState
}

const sortParam = (key: string) => `${key}.sort`
const filterParam = (key: string, column: string) => `${key}.f.${column}`
const columnParam = (key: string) => `${key}.col`
const groupParam = (key: string) => `${key}.group`
const NO_GROUPING = 'none'
const searchParam = ({ key, search }: DataTableParamsOptions) => search ?? `${key}.q`

/** The grid's state as `params` hold it; filters on columns without a header filter are ignored. */
export function readDataTableParams(params: URLSearchParams, options: DataTableParamsOptions): DataTableParamsState {
  const { key, filters, optional = [] } = options
  const sorting = params
    .getAll(sortParam(key))
    .filter((s) => s !== '' && s !== '-')
    .map((s) => (s.startsWith('-') ? { id: s.slice(1), desc: true } : { id: s, desc: false }))
  const columnFilters: ColumnFiltersState = []
  for (const [id, kind] of Object.entries(filters)) {
    const values = params.getAll(filterParam(key, id)).filter((v) => v !== '')
    if (values.length === 0) continue
    if (kind === 'values') columnFilters.push({ id, value: values })
    else if (kind === 'toggle') columnFilters.push({ id, value: true })
    else columnFilters.push({ id, value: values[0] })
  }
  const shown = new Set(params.getAll(columnParam(key)))
  return {
    sorting,
    columnFilters,
    globalFilter: params.get(searchParam(options)) ?? '',
    columnVisibility: Object.fromEntries(optional.map((id) => [id, shown.has(id)])),
    ...(options.grouping && { grouping: readGrouping(params.get(groupParam(key)), options.grouping) }),
  }
}

function readGrouping(param: string | null, groupable: readonly string[]): GroupingState {
  if (param === NO_GROUPING) return []
  const id = param !== null && groupable.includes(param) ? param : groupable[0]
  return id === undefined ? [] : [id]
}

/** Writes the grid's state into `params`, replacing its own params and leaving others alone. */
export function writeDataTableParams(
  params: URLSearchParams,
  options: DataTableParamsOptions,
  state: DataTableParamsState,
): void {
  const { key, filters, optional = [] } = options
  params.delete(sortParam(key))
  for (const { id, desc } of state.sorting) params.append(sortParam(key), desc ? `-${id}` : id)

  for (const id of Object.keys(filters)) params.delete(filterParam(key, id))
  for (const { id, value } of state.columnFilters) {
    const kind = filters[id]
    if (kind === 'values') for (const v of value as string[]) params.append(filterParam(key, id), v)
    else if (kind === 'toggle') params.set(filterParam(key, id), '1')
    else if (kind === 'text') params.set(filterParam(key, id), String(value))
  }

  if (state.globalFilter) params.set(searchParam(options), state.globalFilter)
  else params.delete(searchParam(options))

  params.delete(columnParam(key))
  for (const id of optional) if (state.columnVisibility[id]) params.append(columnParam(key), id)

  if (options.grouping && state.grouping) {
    const [id = NO_GROUPING] = state.grouping
    if (id === options.grouping[0]) params.delete(groupParam(key))
    else params.set(groupParam(key), id)
  }
}

const apply = <T,>(updater: Updater<T>, previous: T): T =>
  typeof updater === 'function' ? (updater as (old: T) => T)(previous) : updater

/**
 * A grid's sort, filters, search and shown columns, kept in the URL (see the module
 * comment). Spread `tableOptions` into `useDataTable`; pair `shown`/`setShown` with a
 * `ColumnPicker`. Changes replace the history entry, as typing in a search box does.
 * Keep `options` stable (e.g. a module constant).
 */
export function useDataTableParams(options: DataTableParamsOptions) {
  const [params, setParams] = useSearchParams()
  const state = useMemo(() => readDataTableParams(params, options), [params, options])

  const update = useCallback(
    (change: (state: DataTableParamsState) => Partial<DataTableParamsState>) =>
      setParams(
        (p) => {
          const current = readDataTableParams(p, options)
          writeDataTableParams(p, options, { ...current, ...change(current) })
          return p
        },
        { replace: true },
      ),
    [setParams, options],
  )

  const tableOptions = useMemo(
    () => ({
      state,
      onSortingChange: (u: Updater<SortingState>) => update((s) => ({ sorting: apply(u, s.sorting) })),
      onColumnFiltersChange: (u: Updater<ColumnFiltersState>) =>
        update((s) => ({ columnFilters: apply(u, s.columnFilters) })),
      onGlobalFilterChange: (u: Updater<string>) =>
        update((s) => ({ globalFilter: apply(u, s.globalFilter) ?? '' })),
      onColumnVisibilityChange: (u: Updater<ColumnVisibilityState>) =>
        update((s) => ({ columnVisibility: apply(u, s.columnVisibility) })),
      onGroupingChange: (u: Updater<GroupingState>) => update((s) => ({ grouping: apply(u, s.grouping ?? []) })),
    }),
    [state, update],
  )

  const shown = useMemo(
    () => new Set(Object.entries(state.columnVisibility).filter(([, v]) => v).map(([id]) => id)),
    [state.columnVisibility],
  )
  const setShown = useCallback(
    (id: string, visible: boolean) => update((s) => ({ columnVisibility: { ...s.columnVisibility, [id]: visible } })),
    [update],
  )

  return { tableOptions, shown: shown as ReadonlySet<string>, setShown }
}
