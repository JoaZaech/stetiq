import { type ComponentProps, useEffect, useId, useMemo, useRef, useState } from 'react'
import { ChevronDown, ChevronRight, PanelRightOpen } from 'lucide-react'
import { CLASSIFICATION_LABEL, isCosmetic } from '@/api/ontology-diff'
import { ClassificationBadge } from '@/components/OntologyDiff'
import { SeveritySwatch } from '@/components/SeveritySwatch'
import { Button } from '@/components/ui/button'
import { formatCount } from '@/lib/format'
import { cn } from '@/lib/utils'
import { CONCEPT_NOUN } from '../concepts'
import type { PatternLink } from '../map/ontology-map'
import type { MapSelection } from '../map/ontology-map-focus'
import { MapSidePanel, type MapPanelNav } from '../map/MapSidePanel'
import {
  type ChangeStatement,
  type ConceptChanges,
  type LevelCount,
  descriptionPreviewOf,
  type OntologyComparison,
  selectionOf,
  summarizeChanges,
  summaryConceptOf,
} from './ontology-map-comparison'
import { SEVERITY } from '@/components/severity-style'

/**
 * The change summary, in a comparison's Map panel while nothing is selected: a count per
 * level, then each changed Concept's changes, the most severe first. Linked with the Map
 * both ways: pointing at an entry previews its Concept's focus (`onPreview`), clicking
 * selects it (`onSelect`), and the entry of `returnTo`, the selection the panel came back
 * from, is highlighted and scrolled to. An entry selects what the Map selects for its
 * Concept, among the links `shown` (`selectionOf`).
 */
export function MapChangeSummary({
  comparison,
  shown,
  returnTo,
  onPreview,
  onSelect,
  nav,
}: {
  comparison: OntologyComparison
  /** The Pattern links the Map shows. */
  shown: readonly PatternLink[]
  returnTo: MapSelection | null
  onPreview: (selection: MapSelection | null) => void
  onSelect: (selection: MapSelection) => void
  nav: MapPanelNav
}) {
  const summary = useMemo(() => summarizeChanges(comparison), [comparison])
  const link: MapLink = {
    current: summaryConceptOf(comparison, summary, returnTo),
    locate: ({ kind, label }) => selectionOf(comparison, { kind: CONCEPT_NOUN[kind], label }, shown),
    onPreview,
    onSelect,
  }
  return (
    <MapSidePanel label="Change summary" title="Changes" nav={nav}>
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
            <CosmeticChanges
              concepts={summary.cosmetic}
              count={summary.counts.find((c) => isCosmetic(c.level))?.count ?? 0}
              link={link}
              previewOf={(c) => descriptionPreviewOf(comparison, c)}
            />
          )}
        </>
      )}
    </MapSidePanel>
  )
}

/** The change summary collapsed to a thin rail: its headline counts, and a button to expand it. */
export function MapChangesRail({ comparison, onExpand }: { comparison: OntologyComparison; onExpand: () => void }) {
  const { counts } = useMemo(() => summarizeChanges(comparison), [comparison])
  return (
    <aside aria-label="Changes collapsed" className="flex w-14 shrink-0 flex-col items-center gap-4 border-l bg-background py-3 text-sm">
      <Button variant="ghost" size="icon-sm" aria-label="Expand panel" onClick={onExpand}>
        <PanelRightOpen aria-hidden />
      </Button>
      <LevelCounts role="status" stacked counts={counts} className="font-medium" />
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
 * colours for severity, none for cosmetic changes, which the Diff colours are not for)
 * after its swatch, so the counts are the severity key. `stacked`, one count per line,
 * each level named only to screen readers and on hover, as on the collapsed rail.
 */
export function LevelCounts({
  counts,
  stacked = false,
  className,
  ...props
}: { counts: LevelCount[]; stacked?: boolean } & ComponentProps<'p'>) {
  return (
    <p className={cn(stacked ? 'flex flex-col items-center gap-3' : 'flex flex-wrap items-center gap-x-1.5', className)} {...props}>
      {counts.map(({ level, count }, i) => (
        <span key={level} className="flex items-center gap-1" title={stacked ? CLASSIFICATION_LABEL[level] : undefined}>
          {!stacked && i > 0 && ' · '}
          <SeveritySwatch level={level} />
          <span className={SEVERITY.text[level]}>
            {count}
            <span className={cn(stacked && 'sr-only')}> {CLASSIFICATION_LABEL[level]}</span>
          </span>
        </span>
      ))}
    </p>
  )
}

/**
 * The cosmetic (documentation-only) changes, collapsed to one line that expands to their entries.
 * It opens by itself when the Map selects one of them. Each entry previews its new
 * description (`previewOf`).
 */
function CosmeticChanges({
  concepts,
  count,
  link,
  previewOf,
}: {
  concepts: ConceptChanges[]
  count: number
  link: MapLink
  previewOf: (concept: ConceptChanges) => string | null
}) {
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
          <SummaryEntry key={`${c.kind}:${c.label}`} concept={c} link={link} preview={previewOf(c)} />
        ))}
      </ul>
    </div>
  )
}

/** One changed Concept's entry; `preview`, a documentation-only one's new description, on one line. */
function SummaryEntry({
  concept,
  link,
  preview = null,
}: {
  concept: ConceptChanges
  link: MapLink
  preview?: string | null
}) {
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
        {preview && (
          <span title={preview} className="block truncate text-xs text-muted-foreground">
            {preview}
          </span>
        )}
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
