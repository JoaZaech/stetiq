import { type ComponentProps, useEffect, useId, useMemo, useRef, useState } from 'react'
import { ChevronDown, ChevronRight } from 'lucide-react'
import { CLASSIFICATION_LABEL } from '@/api/ontology-diff'
import { ClassificationBadge } from '@/components/OntologyDiff'
import { formatCount } from '@/lib/format'
import { cn } from '@/lib/utils'
import { CONCEPT_NOUN } from '../concepts'
import type { PatternLink } from '../map/ontology-map'
import type { MapSelection } from '../map/ontology-map-focus'
import {
  type ChangeStatement,
  type ConceptChanges,
  type LevelCount,
  type OntologyComparison,
  selectionOf,
  summarizeChanges,
  summaryConceptOf,
} from './ontology-map-comparison'
import { SEVERITY } from './severity-style'

/**
 * The change summary beside a comparison's Map: a count per level, then each changed
 * Concept's changes, the most severe first. Linked with the Map both ways: pointing at an
 * entry previews its Concept's focus (`onPreview`), clicking selects it (`onSelect`), and
 * the entry of the Map's `selection` is highlighted and scrolled to. An entry selects what
 * the Map selects for its Concept, among the links `shown` (`selectionOf`).
 */
export function MapChangeSummary({
  comparison,
  shown,
  selection,
  onPreview,
  onSelect,
}: {
  comparison: OntologyComparison
  /** The Pattern links the Map shows. */
  shown: readonly PatternLink[]
  selection: MapSelection | null
  onPreview: (selection: MapSelection | null) => void
  onSelect: (selection: MapSelection) => void
}) {
  const summary = useMemo(() => summarizeChanges(comparison), [comparison])
  const link: MapLink = {
    current: summaryConceptOf(comparison, summary, selection),
    locate: ({ kind, label }) => selectionOf(comparison, { kind: CONCEPT_NOUN[kind], label }, shown),
    onPreview,
    onSelect,
  }
  return (
    <aside aria-label="Change summary" className="w-72 shrink-0 space-y-3 overflow-y-auto border-r bg-background p-4 text-sm">
      <h3 className="font-semibold">Changes</h3>
      {comparison.diff.changes.length === 0 ? (
        <p className="text-muted-foreground">No changes between the two versions.</p>
      ) : (
        <>
          <LevelCounts role="status" className="font-medium" counts={summary.counts} />
          {summary.concepts.length > 0 && (
            <ul aria-label="Changed Concepts" className="space-y-1">
              {summary.concepts.map((c) => (
                <SummaryEntry key={`${c.kind}:${c.label}`} concept={c} link={link} />
              ))}
            </ul>
          )}
          {summary.cosmetic.length > 0 && (
            <DocumentationOnly
              concepts={summary.cosmetic}
              count={summary.counts.find((c) => c.level === 'cosmetic')?.count ?? 0}
              link={link}
            />
          )}
        </>
      )}
    </aside>
  )
}

/**
 * How the summary is linked with the Map: the entry of the Map's selection, where an
 * entry's Concept is on the Map (null when not shown), and what pointing at an entry
 * (`onPreview`) and clicking it (`onSelect`) do.
 */
interface MapLink {
  current: ConceptChanges | null
  locate: (concept: ConceptChanges) => MapSelection | null
  onPreview: (selection: MapSelection | null) => void
  onSelect: (selection: MapSelection) => void
}

/**
 * The headline: a count per level, the weightiest first, each in its own colour (the Diff
 * colours for severity, none for cosmetic changes, which the Diff colours are not for).
 */
export function LevelCounts({ counts, ...props }: { counts: LevelCount[] } & ComponentProps<'p'>) {
  return (
    <p {...props}>
      {counts.map(({ level, count }, i) => (
        <span key={level}>
          {i > 0 && ' · '}
          <span className={SEVERITY.text[level]}>
            {count} {CLASSIFICATION_LABEL[level]}
          </span>
        </span>
      ))}
    </p>
  )
}

/**
 * The cosmetic (documentation-only) changes, collapsed to one line that expands to their entries.
 * It opens by itself when the Map selects one of them.
 */
function DocumentationOnly({ concepts, count, link }: { concepts: ConceptChanges[]; count: number; link: MapLink }) {
  const id = useId()
  const [expanded, setExpanded] = useState(false)
  const open = expanded || (link.current !== null && concepts.includes(link.current))
  const Chevron = open ? ChevronDown : ChevronRight
  return (
    <div className="space-y-1">
      <button
        type="button"
        aria-expanded={open}
        aria-controls={id}
        onClick={() => setExpanded(!open)}
        className="flex w-full items-center gap-1 rounded-md p-2 text-left text-muted-foreground hover:bg-muted"
      >
        <Chevron aria-hidden className="size-4 shrink-0" />
        {formatCount(count, 'documentation-only change')}
      </button>
      <ul id={id} hidden={!open} aria-label="Documentation-only changes" className="space-y-1">
        {concepts.map((c) => (
          <SummaryEntry key={`${c.kind}:${c.label}`} concept={c} link={link} />
        ))}
      </ul>
    </div>
  )
}

function SummaryEntry({ concept, link }: { concept: ConceptChanges; link: MapLink }) {
  const { onPreview, onSelect } = link
  const current = concept === link.current
  const selection = link.locate(concept)
  const ref = useRef<HTMLLIElement>(null)
  useEffect(() => {
    if (current) ref.current?.scrollIntoView({ block: 'nearest' })
  }, [current])
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
      {text} <span className="text-muted-foreground">({CLASSIFICATION_LABEL[level]})</span>
    </span>
  )
}
