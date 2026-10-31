import { useId, type KeyboardEvent } from 'react'
import type { ClassOrRelation } from '../concepts'
import { MapSidePanel, type MapPanelNav } from './MapSidePanel'
import type { SearchResults } from './ontology-map-search'

/**
 * The Map's search results, in its panel: the Concepts the search names, then the other
 * Concepts it mentions, each with its reasons. Picking one (click, or Enter on it; the
 * arrow keys move between them) calls `onPick`; a result `canPick` rejects, such as one a
 * filter hides, is disabled.
 */
export function MapSearchResults({
  query,
  results,
  canPick,
  onPick,
  nav,
}: {
  query: string
  results: SearchResults
  canPick: (result: ClassOrRelation) => boolean
  onPick: (result: ClassOrRelation) => void
  nav: MapPanelNav
}) {
  const empty = results.names.length === 0 && results.others.length === 0
  return (
    <MapSidePanel label="Search results" kind="Search" title={`“${query.trim()}”`} nav={nav} onKeyDown={moveFocus}>
      {empty ? (
        <p className="text-muted-foreground">Nothing matches “{query.trim()}”.</p>
      ) : (
        <>
          <ResultGroup title="Name matches" results={results.names} canPick={canPick} onPick={onPick} />
          <ResultGroup title="Other matches" results={results.others} canPick={canPick} onPick={onPick} />
        </>
      )}
    </MapSidePanel>
  )
}

function ResultGroup({
  title,
  results,
  canPick,
  onPick,
}: {
  title: string
  results: (ClassOrRelation & { reasons?: string[] })[]
  canPick: (result: ClassOrRelation) => boolean
  onPick: (result: ClassOrRelation) => void
}) {
  const id = useId()
  if (results.length === 0) return null
  return (
    <section className="space-y-1">
      <h3 id={id} className="text-xs font-semibold text-muted-foreground">
        {title}
      </h3>
      <ul aria-labelledby={id} className="space-y-1">
        {results.map((r) => (
          <li key={`${r.kind}:${r.label}`}>
            <button
              type="button"
              disabled={!canPick(r)}
              onClick={() => onPick(r)}
              className="w-full rounded-sm px-2 py-1 text-left hover:bg-muted focus-visible:bg-muted focus-visible:outline-none disabled:cursor-not-allowed disabled:opacity-50"
            >
              <span className="font-medium break-words">{r.label}</span>{' '}
              <span className="text-xs text-muted-foreground">{r.kind}</span>
              {r.reasons && (
                <span className="block text-xs text-muted-foreground">
                  <Reason text={r.reasons.join('; ')} />
                </span>
              )}
            </button>
          </li>
        ))}
      </ul>
    </section>
  )
}

/** A reason with its `backticked` names set as code. */
function Reason({ text }: { text: string }) {
  return text.split('`').map((part, i) =>
    i % 2 === 1 ? (
      <code key={i} className="font-mono">
        {part}
      </code>
    ) : (
      part
    ),
  )
}

/** ArrowUp and ArrowDown move focus between the results that can be picked. */
function moveFocus(e: KeyboardEvent<HTMLElement>) {
  if (e.key !== 'ArrowDown' && e.key !== 'ArrowUp') return
  const buttons = [...e.currentTarget.querySelectorAll<HTMLButtonElement>('button:not(:disabled)')]
  if (buttons.length === 0) return
  e.preventDefault()
  const at = buttons.indexOf(document.activeElement as HTMLButtonElement)
  const next = e.key === 'ArrowDown' ? Math.min(at + 1, buttons.length - 1) : Math.max(at - 1, 0)
  buttons[next].focus()
}
