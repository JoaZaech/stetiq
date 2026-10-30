/**
 * URL state of a list page with optional columns and a chart view (the Ontology Version
 * and Construction Run lists), so links keep what the user sees:
 *
 * - `?view=chart`: the Table/Chart toggle (absent = table);
 * - `?col=<column id>` (repeated): the optional columns shown in the table, named by
 *   `paramColumnId`/`metricColumnId`, e.g. `?col=param:extractor&col=metric:recall`;
 * - `?charts=<text>`: the "Search metric charts" filter.
 */
import { useCallback, useMemo } from 'react'
import { useSearchParams } from 'react-router'
import { useViewParam } from './view-param'

export type ViewMode = 'table' | 'chart'

const VIEW_MODES: readonly [ViewMode, ...ViewMode[]] = ['table', 'chart']

/** The Table/Chart toggle, kept in `?view=`. Switching adds a history entry. */
export function useViewMode(): [ViewMode, (mode: ViewMode) => void] {
  return useViewParam(VIEW_MODES)
}

/** Column ids of a table's optional columns, as the `ColumnPicker` and the URL name them. */
export const paramColumnId = (key: string) => `param:${key}`
export const metricColumnId = (key: string) => `metric:${key}`

const COLUMN_PARAM = 'col'

/** The optional columns shown in the table, kept as repeated `?col=`, and a toggle for one. */
export function useShownColumns(): [ReadonlySet<string>, (id: string, visible: boolean) => void] {
  const [params, setParams] = useSearchParams()
  const shown = useMemo(() => new Set(params.getAll(COLUMN_PARAM)), [params])
  const setShown = useCallback(
    (id: string, visible: boolean) =>
      setParams(
        (p) => {
          const rest = p.getAll(COLUMN_PARAM).filter((c) => c !== id)
          p.delete(COLUMN_PARAM)
          for (const c of visible ? [...rest, id] : rest) p.append(COLUMN_PARAM, c)
          return p
        },
        { replace: true },
      ),
    [setParams],
  )
  return [shown, setShown]
}

/** The "Search metric charts" text, kept in `?charts=`. */
export function useChartSearch(): [string, (search: string) => void] {
  const [params, setParams] = useSearchParams()
  const search = params.get('charts') ?? ''
  const setSearch = useCallback(
    (next: string) =>
      setParams(
        (p) => {
          if (next) p.set('charts', next)
          else p.delete('charts')
          return p
        },
        { replace: true },
      ),
    [setParams],
  )
  return [search, setSearch]
}
