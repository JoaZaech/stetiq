import { useCallback, useMemo } from 'react'
import { useSearchParams } from 'react-router'
import { parseRunFilters, type RunFilters } from './runs'

/**
 * The run list's status and time-range filters, kept in the URL so the view can be
 * shared (`?status=failed&range=7d`). Defaults are left out of the URL. The shown
 * columns and the view mode are in `@/lib/metric-view-params`.
 */
export function useRunFilters() {
  const [searchParams, setSearchParams] = useSearchParams()
  const filters = useMemo(() => parseRunFilters(searchParams), [searchParams])

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

  return { filters, setFilter }
}
