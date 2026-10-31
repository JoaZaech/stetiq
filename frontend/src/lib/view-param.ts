import { useCallback } from 'react'
import { useSearchParams } from 'react-router'
import { setOrDeleteParam } from './search-params'

/**
 * A page's view toggle, kept in `?view=` so links open in the same view. The first of
 * `modes` is the default and leaves `?view=` out; an unknown value falls back to it.
 * Switching adds a history entry and keeps the other search params.
 */
export function useViewParam<M extends string>(modes: readonly [M, ...M[]]): [M, (mode: M) => void] {
  const [params, setParams] = useSearchParams()
  const fallback = modes[0]
  const value = params.get('view')
  const mode = modes.find((m) => m === value) ?? fallback
  const setMode = useCallback(
    (next: M) =>
      setParams((p) => setOrDeleteParam(p, 'view', next === fallback ? null : next)),
    [setParams, fallback],
  )
  return [mode, setMode]
}
