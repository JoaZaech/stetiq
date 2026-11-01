import { useCallback } from 'react'
import { useSearchParams } from 'react-router'
import { setOrDeleteParam } from './search-params'

/**
 * The open side sheet, kept in `?sheet=` as `kind:id` (`question:customer-names`), so a
 * sheet can be linked and survives a reload. One param, so one sheet at a time.
 */
export const SHEET_PARAM = 'sheet'

/** Which sheet is open: what it is about (`kind`) and that thing's id. */
export interface SheetRef<K extends string = string> {
  kind: K
  id: string
}

/** The sheet `value` (a `?sheet=` param) names; null when absent, not one, or of another kind. */
export function parseSheet<K extends string>(value: string | null, kinds: readonly K[]): SheetRef<K> | null {
  if (!value) return null
  const colon = value.indexOf(':')
  const kind = kinds.find((k) => k === value.slice(0, colon))
  const id = value.slice(colon + 1)
  return colon > 0 && kind !== undefined && id !== '' ? { kind, id } : null
}

/** `sheet` as a `?sheet=` value. */
export function formatSheet(sheet: SheetRef): string {
  return `${sheet.kind}:${sheet.id}`
}

/**
 * The page's open sheet among `kinds` (pass a stable array). Opening adds a history entry,
 * so the browser's Back closes the sheet; closing replaces it, so Back does not reopen it.
 * Both keep the other search params.
 */
export function useSheetParam<K extends string>(kinds: readonly K[]) {
  const [params, setParams] = useSearchParams()
  const sheet = parseSheet(params.get(SHEET_PARAM), kinds)
  const openSheet = useCallback(
    (next: SheetRef<K>) => setParams((p) => setOrDeleteParam(p, SHEET_PARAM, formatSheet(next))),
    [setParams],
  )
  const closeSheet = useCallback(
    () => setParams((p) => setOrDeleteParam(p, SHEET_PARAM, null), { replace: true }),
    [setParams],
  )
  return { sheet, openSheet, closeSheet }
}
