import { type ComponentProps, Fragment, useEffect, useId, useMemo, useRef, useState } from 'react'
import { ChevronDown, ChevronRight, PanelRightOpen } from 'lucide-react'
import { type Classification, CLASSIFICATION_LABEL, isCosmetic } from '@/api/ontology-diff'
import { SeveritySwatch } from '@/components/SeveritySwatch'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import { CONCEPT_NOUN } from '../concepts'
import type { PatternLink } from '../map/ontology-map'
import type { MapSelection } from '../map/ontology-map-focus'
import { MapSidePanel, type MapPanelNav } from '../map/MapSidePanel'
import {
  type ChangeStatement,
  type ConceptChanges,
  type LevelCount,
  type OntologyComparison,
  selectionOf,
  summarizeChanges,
  summaryConceptOf,
  type SummarySection,
} from './ontology-map-comparison'
import { SEVERITY } from '@/components/severity-style'

/**
 * The change summary, in a comparison's Map panel while nothing is selected: a count per
 * level, then a section per level of the changed Concepts whose most severe change is at
 * it, the most severe first, documentation-only collapsed. Linked with the Map
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
          {summary.sections.map((section) => (
            <LevelSection key={section.level} section={section} link={link} />
          ))}
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
 * One level's section: its heading, in the level's colour with its count of Concepts, then
 * their entries. The documentation-only one is collapsed to its heading, and opens by
 * itself when the Map selects one of its Concepts.
 */
function LevelSection({ section: { level, concepts }, link }: { section: SummarySection; link: MapLink }) {
  const id = useId()
  const collapsible = isCosmetic(level)
  const [expanded, setExpanded] = useState(false)
  const open = !collapsible || expanded || (link.current !== null && concepts.includes(link.current))
  const Chevron = open ? ChevronDown : ChevronRight
  const label = (
    <>
      <span id={`${id}-name`}>{headingOf(level)}</span> <span className="tabular-nums">{concepts.length}</span>
    </>
  )
  return (
    <section aria-labelledby={`${id}-name`} className="space-y-1">
      <h4 className={cn('font-semibold', SEVERITY.text[level])}>
        {collapsible ? (
          <button
            type="button"
            aria-expanded={open}
            aria-controls={`${id}-entries`}
            onClick={() => setExpanded(!open)}
            className="flex w-full items-center gap-1 rounded-md py-1 text-left hover:bg-muted"
          >
            <Chevron aria-hidden className="size-4 shrink-0" />
            {label}
          </button>
        ) : (
          label
        )}
      </h4>
      <ul id={`${id}-entries`} hidden={!open} className="space-y-1">
        {concepts.map((c) => (
          <SummaryEntry key={`${c.kind}:${c.label}`} concept={c} link={link} />
        ))}
      </ul>
    </section>
  )
}

/** A level as a section heading names it, e.g. "Documentation-only". */
const headingOf = (level: Classification) => CLASSIFICATION_LABEL[level].replace(/^./, (c) => c.toUpperCase())

/** An entry: the Concept's name on its own full-width line, its kind, then its changes. */
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
        <span data-concept-name className="block font-semibold break-normal wrap-normal">
          <BreakAtUnderscores name={concept.label} />
        </span>
        <span className="block text-xs text-muted-foreground">{CONCEPT_NOUN[concept.kind]}</span>
        {concept.statements.map((s) => (
          <Statement key={`${s.change.concept}:${s.change.detail}`} statement={s} />
        ))}
      </button>
    </li>
  )
}

/** `name`, which may break after each `_` and nowhere else: `HAS_STOP_TIME` never wraps mid-word. */
function BreakAtUnderscores({ name }: { name: string }) {
  return name.split(/(?<=_)/).map((part, i) => (
    <Fragment key={i}>
      {i > 0 && <wbr />}
      {part}
    </Fragment>
  ))
}

/**
 * One change in words, e.g. "attribute `wheelchair_boarding` added (additive)", naming its
 * level only when it differs from its section's.
 */
function Statement({ statement: { attribute, text, level } }: { statement: ChangeStatement }) {
  return (
    <span className="block text-xs">
      {attribute !== null && (
        <>
          attribute <code className="font-mono">{attribute}</code>{' '}
        </>
      )}
      {text}
      {level !== null && <span className="text-muted-foreground"> ({CLASSIFICATION_LABEL[level]})</span>}
    </span>
  )
}
