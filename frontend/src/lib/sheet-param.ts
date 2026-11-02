import { useCallback } from 'react'
import { useLocation, useNavigate, useSearchParams } from 'react-router'
import { setOrDeleteParam } from './search-params'

/**
 * The open side sheet, kept in `?sheet=` as `kind:id` (`question:customer-names`), so a
 * sheet can be linked and survives a reload. One param, so one sheet at a time.
 */
export const SHEET_PARAM = 'sheet'

/**
 * The sheet the open one was opened from, whose content it replaced (`?sheet-back=`, e.g.
 * `consumer:triage-bot` while `?sheet=question:agent-names`): its **Back** returns there.
 */
export const SHEET_BACK_PARAM = 'sheet-back'

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

/** The open sheet and the one its Back returns to; `back` is null without an open sheet. */
export function parseSheetParams<K extends string>(
  params: URLSearchParams,
  kinds: readonly K[],
): { sheet: SheetRef<K> | null; back: SheetRef<K> | null } {
  const sheet = parseSheet(params.get(SHEET_PARAM), kinds)
  return { sheet, back: sheet && parseSheet(params.get(SHEET_BACK_PARAM), kinds) }
}

/** Marks a history entry `openSheet` pushed from another sheet, so Back can pop it. */
interface SheetHistoryState {
  sheetFrom?: string
}

/**
 * The page's open sheet among `kinds` (pass a stable array). Opening adds a history entry,
 * so the browser's Back closes the sheet; closing replaces it, so Back does not reopen it.
 * All keep the other search params.
 *
 * Opening a sheet `from` another replaces that sheet's content and keeps `from` in
 * `?sheet-back=`; `goBack` returns to it. When this page pushed that step, `goBack` is the
 * browser's Back (so history has no duplicate entry); after a reload or on a shared link,
 * it replaces the entry with `from`.
 */
export function useSheetParam<K extends string>(kinds: readonly K[]) {
  const [params, setParams] = useSearchParams()
  const location = useLocation()
  const navigate = useNavigate()
  const { sheet, back } = parseSheetParams(params, kinds)
  const openSheet = useCallback(
    (next: SheetRef<K>, from?: SheetRef<K>) =>
      setParams(
        (p) => {
          setOrDeleteParam(p, SHEET_PARAM, formatSheet(next))
          return setOrDeleteParam(p, SHEET_BACK_PARAM, from && formatSheet(from))
        },
        { state: from ? ({ sheetFrom: formatSheet(from) } satisfies SheetHistoryState) : undefined },
      ),
    [setParams],
  )
  const closeSheet = useCallback(
    () =>
      setParams(
        (p) => {
          setOrDeleteParam(p, SHEET_PARAM, null)
          return setOrDeleteParam(p, SHEET_BACK_PARAM, null)
        },
        { replace: true },
      ),
    [setParams],
  )
  const pushedFrom = (location.state as SheetHistoryState | null)?.sheetFrom
  const goBack = useCallback(() => {
    if (!back) return
    if (pushedFrom === formatSheet(back)) {
      navigate(-1)
      return
    }
    setParams(
      (p) => {
        setOrDeleteParam(p, SHEET_PARAM, formatSheet(back))
        return setOrDeleteParam(p, SHEET_BACK_PARAM, null)
      },
      { replace: true },
    )
  }, [back, pushedFrom, navigate, setParams])
  return { sheet, back, openSheet, closeSheet, goBack }
}
