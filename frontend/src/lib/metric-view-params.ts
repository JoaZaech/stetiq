/**
 * URL state of a list page with metric columns and a chart view (the Ontology Version
 * list; the Construction Run list reuses it), so links keep what the user sees:
 *
 * - `?view=chart`: the Table/Chart toggle (absent = table);
 * - `?metric=<key>` (repeated): the metric columns shown in the table;
 * - `?charts=<text>`: the "Search metric charts" filter.
 */
import { useCallback } from 'react'
import { useSearchParams } from 'react-router'

export type ViewMode = 'table' | 'chart'

/** The Table/Chart toggle, kept in `?view=`. Switching adds a history entry. */
export function useViewMode(): [ViewMode, (mode: ViewMode) => void] {
  const [params, setParams] = useSearchParams()
  const mode: ViewMode = params.get('view') === 'chart' ? 'chart' : 'table'
  const setMode = useCallback(
    (next: ViewMode) =>
      setParams((p) => {
        if (next === 'chart') p.set('view', 'chart')
        else p.delete('view')
        return p
      }),
    [setParams],
  )
  return [mode, setMode]
}

/** The metric columns shown in the table, kept as repeated `?metric=`. */
export function useMetricColumns(): [string[], (metrics: string[]) => void] {
  const [params, setParams] = useSearchParams()
  const metrics = params.getAll('metric')
  const setMetrics = useCallback(
    (next: string[]) =>
      setParams(
        (p) => {
          p.delete('metric')
          for (const metric of next) p.append('metric', metric)
          return p
        },
        { replace: true },
      ),
    [setParams],
  )
  return [metrics, setMetrics]
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
