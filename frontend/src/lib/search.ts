/** The search param every list page keeps its search box in, so a search can be shared. */
export const SEARCH_PARAM = 'q'

/**
 * Whether a row matches a list page's search: every word of `query` occurs, case-blind, in
 * one of `fields` (an id, a param value, a version, a question). An empty query matches all.
 */
export function matchesSearch(query: string, fields: readonly (string | number | null | undefined)[]): boolean {
  const words = query.trim().toLowerCase().split(/\s+/).filter(Boolean)
  if (words.length === 0) return true
  const haystack = fields
    .filter((f) => f !== null && f !== undefined)
    .map((f) => String(f).toLowerCase())
    .join('\u0000')
  return words.every((word) => haystack.includes(word))
}

/** One page of `items`: `page` is 1-based and clamped to the pages there are. */
export function pageOf<T>(items: readonly T[], page: number, size: number): { items: T[]; page: number; pageCount: number } {
  const pageCount = Math.max(1, Math.ceil(items.length / size))
  const current = Math.min(Math.max(1, Math.trunc(page) || 1), pageCount)
  return { items: items.slice((current - 1) * size, current * size), page: current, pageCount }
}
