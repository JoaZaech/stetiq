import { useCallback, useMemo } from 'react'
import { useSearchParams } from 'react-router'
import { parseRunFilters, type RunFilters } from './runs'

/** Search param naming each optional column shown, e.g. `?col=param:extractor&col=metric:recall`. */
const COLUMN_PARAM = 'col'

/**
 * The run list's view, kept in the URL so it can be shared: the status and time-range
 * filters and the optional (param/metric) columns shown. Defaults are left out of the URL.
 */
export function useRunListParams() {
  const [searchParams, setSearchParams] = useSearchParams()
  const filters = useMemo(() => parseRunFilters(searchParams), [searchParams])
  const columns = useMemo(() => new Set(searchParams.getAll(COLUMN_PARAM)), [searchParams])

  const setFilter = useCallback(
    <K extends keyof RunFilters>(key: K, value: RunFilters[K]) =>
      setSearchParams(
        (params) => {
          if (value === 'all') params.delete(key)
          else params.set(key, value)
          return params
        },
        { replace: true },
      ),
    [setSearchParams],
  )

  const setColumn = useCallback(
    (id: string, visible: boolean) =>
      setSearchParams(
        (params) => {
          const shown = params.getAll(COLUMN_PARAM).filter((c) => c !== id)
          params.delete(COLUMN_PARAM)
          for (const c of visible ? [...shown, id] : shown) params.append(COLUMN_PARAM, c)
          return params
        },
        { replace: true },
      ),
    [setSearchParams],
  )

  return { filters, setFilter, columns, setColumn }
}
