import { useCallback } from 'react'
import { useSearchParams } from 'react-router'
import { setOrDeleteParam } from '@/lib/search-params'
import { SEARCH_PARAM } from '@/lib/search'

/**
 * A URL search param as `[value, setValue]`, replacing the history entry as it changes so
 * typing does not fill Back. `name` defaults to the list search (`?q=`).
 */
export function useSearchParam(name: string = SEARCH_PARAM): [string, (value: string) => void] {
  const [params, setParams] = useSearchParams()
  const value = params.get(name) ?? ''
  const setValue = useCallback(
    (next: string) => setParams((p) => setOrDeleteParam(p, name, next), { replace: true }),
    [name, setParams],
  )
  return [value, setValue]
}
