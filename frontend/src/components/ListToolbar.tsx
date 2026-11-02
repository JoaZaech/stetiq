import type { ReactNode } from 'react'
import { SearchInput } from './SearchInput'

/**
 * The one toolbar row every list page has, MLflow-style: the search box, then filters,
 * then the page's actions on the right (Columns, Compare, the main button). Pair it with
 * `ListCount` under the list.
 */
export function ListToolbar({
  search,
  onSearch,
  searchLabel,
  children,
  actions,
}: {
  search: string
  onSearch: (value: string) => void
  /** Names the search box, e.g. "Search runs". */
  searchLabel: string
  /** Filters, after the search box. */
  children?: ReactNode
  /** On the right. */
  actions?: ReactNode
}) {
  return (
    <div role="toolbar" aria-label="List controls" className="flex flex-wrap items-center gap-2">
      <SearchInput label={searchLabel} value={search} onChange={onSearch} className="w-64" />
      {children}
      {actions && <div className="ml-auto flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  )
}

/** The line under a list: "9 questions", or "3 of 9 questions" while filtered. */
export function ListCount({ shown, total, noun }: { shown: number; total: number; noun: string }) {
  return (
    <p className="text-xs text-muted-foreground tabular-nums" aria-live="polite">
      {shown === total ? `${total} ${noun}` : `${shown} of ${total} ${noun}`}
    </p>
  )
}
