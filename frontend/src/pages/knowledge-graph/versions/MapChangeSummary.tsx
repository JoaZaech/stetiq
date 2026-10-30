import { useEffect, useMemo, useRef } from 'react'
import { ClassificationBadge } from '@/components/OntologyDiff'
import { cn } from '@/lib/utils'
import type { OntologyComparison } from './ontology-map-comparison'
import type { MapSelection } from './ontology-map-focus'
import {
  CONCEPT_NOUN,
  summarizeChanges,
  summaryConceptOf,
  type ChangeLevel,
  type ChangeStatement,
  type ConceptChanges,
} from './ontology-map-summary'

/** Each level's count in the headline, in its own colour: the Diff colours for severity. */
const LEVEL_TEXT: Record<ChangeLevel, string> = {
  additive: 'text-diff-additive',
  deprecating: 'text-diff-deprecating',
  breaking: 'text-diff-breaking',
}

/**
 * The change summary beside a comparison's Map: a count per level, then each changed
 * Concept's changes, the most severe first. Linked with the Map both ways: pointing at an
 * entry previews its Concept's focus (`onPreview`), clicking selects it (`onSelect`), and
 * the entry of the Map's `selection` is highlighted and scrolled to.
 */
export function MapChangeSummary({
  comparison,
  selection,
  onPreview,
  onSelect,
}: {
  comparison: OntologyComparison
  selection: MapSelection | null
  onPreview: (selection: MapSelection | null) => void
  onSelect: (selection: MapSelection) => void
}) {
  const summary = useMemo(() => summarizeChanges(comparison), [comparison])
  const current = summaryConceptOf(comparison, summary, selection)
  return (
    <aside aria-label="Change summary" className="w-72 shrink-0 space-y-3 overflow-y-auto border-r bg-background p-4 text-sm">
      <h3 className="font-semibold">Changes</h3>
      {comparison.diff.changes.length === 0 ? (
        <p className="text-muted-foreground">No changes between the two versions.</p>
      ) : (
        <>
          <p role="status" className="font-medium">
            {summary.counts.map(({ level, count }, i) => (
              <span key={level}>
                {i > 0 && ' · '}
                <span className={LEVEL_TEXT[level]}>
                  {count} {level}
                </span>
              </span>
            ))}
          </p>
          <ul aria-label="Changed Concepts" className="space-y-1">
            {summary.concepts.map((c) => (
              <SummaryEntry
                key={`${c.kind}:${c.label}`}
                concept={c}
                current={c === current}
                onPreview={onPreview}
                onSelect={onSelect}
              />
            ))}
          </ul>
        </>
      )}
    </aside>
  )
}

function SummaryEntry({
  concept,
  current,
  onPreview,
  onSelect,
}: {
  concept: ConceptChanges
  current: boolean
  onPreview: (selection: MapSelection | null) => void
  onSelect: (selection: MapSelection) => void
}) {
  const ref = useRef<HTMLLIElement>(null)
  useEffect(() => {
    if (current) ref.current?.scrollIntoView({ block: 'nearest' })
  }, [current])
  const { selection } = concept
  return (
    <li ref={ref} aria-label={concept.label}>
      <button
        type="button"
        aria-current={current || undefined}
        disabled={!selection}
        onClick={() => selection && onSelect(selection)}
        onMouseEnter={() => onPreview(selection)}
        onMouseLeave={() => onPreview(null)}
        onFocus={() => onPreview(selection)}
        onBlur={() => onPreview(null)}
        className={cn(
          'block w-full space-y-1 rounded-md border border-transparent p-2 text-left hover:bg-muted',
          current && 'border-foreground bg-muted',
        )}
      >
        <span className="flex items-center gap-2">
          <span className="font-semibold break-all">{concept.label}</span>
          <span className="text-xs text-muted-foreground">{CONCEPT_NOUN[concept.kind]}</span>
          <ClassificationBadge classification={concept.level} />
        </span>
        {concept.statements.map((s) => (
          <Statement key={`${s.change.concept}:${s.change.detail}`} statement={s} />
        ))}
      </button>
    </li>
  )
}

/** One change in words, e.g. "attribute `wheelchairBoarding` removed (breaking)". */
function Statement({ statement: { attribute, text, level } }: { statement: ChangeStatement }) {
  return (
    <span className="block text-xs">
      {attribute !== null && (
        <>
          attribute <code className="font-mono">{attribute}</code>{' '}
        </>
      )}
      {text} <span className="text-muted-foreground">({level})</span>
    </span>
  )
}
