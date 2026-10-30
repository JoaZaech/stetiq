import '@xyflow/react/dist/style.css'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  BaseEdge,
  Controls,
  Handle,
  MarkerType,
  Panel,
  Position,
  ReactFlow,
  useInternalNode,
  useReactFlow,
  useStore,
  ViewportPortal,
  type Edge,
  type EdgeProps,
  type InternalNode,
  type Node,
  type NodeProps,
} from '@xyflow/react'
import { CLASSIFICATIONS } from '@/api/ontology-diff'
import type { Ontology } from '@/api/ontology-versions'
import { ErrorAlert } from '@/components/ErrorAlert'
import { ClassificationBadge } from '@/components/OntologyDiff'
import { Label } from '@/components/ui/label'
import { Skeleton } from '@/components/ui/skeleton'
import { Switch } from '@/components/ui/switch'
import { cn } from '@/lib/utils'
import { type ConceptSelection, formatSelection, useConceptSelection } from '../concept-selection'
import type { ClassOrRelation } from '../concepts'
import { ChangeLevelBadge, MapChangeSummary } from '../comparison/MapChangeSummary'
import { MapDetailsPanel } from './MapDetailsPanel'
import { MAP_HEIGHT } from '../map-view'
import { MapPathPanel } from './MapPathPanel'
import { MapSearchResults } from './MapSearchResults'
import { filterOntologyMap, ontologyMap, type LinkRoute, type MapFilters } from './ontology-map'
import {
  changesOf,
  linkChanged,
  type AttributeChange,
  type MapChange,
  type MapChangeKind,
  type OntologyComparison,
} from '../comparison/ontology-map-comparison'
import { centreOf, locatedSelection } from './ontology-map-centre'
import { detailsOf, focusOf, relationSelection, searchMap, type MapSelection } from './ontology-map-focus'
import { layoutOntologyMap, type Point } from './ontology-map-layout'
import { labelShown, linkShape, READABLE_ZOOM, straightPath, type Box } from './ontology-map-links'
import {
  ATTRIBUTE_LINE_HEIGHT,
  ATTRIBUTE_MARKER,
  attributeLine,
  classSizes,
  MONOSPACE_FONT_SIZE,
  NODE_SIZE,
} from './ontology-map-sizes'
import { shortestPaths } from './ontology-map-paths'
import { searchOntology } from './ontology-map-search'
import { levelOf } from '../comparison/ontology-map-summary'
import { SEVERITY, severityStroke } from '../comparison/severity-style'

/**
 * How an item is drawn against the selection and the search: `selected` is the selection
 * itself, `match` a search match, and `faded` is out of the selection's focus or, with no
 * selection, not a match of an active search.
 */
type Emphasis = {
  selected: boolean
  match: boolean
  faded: boolean
}

/** An item's data for how it changed, set on a comparison's Map only. */
type MapChangeData = { change?: MapChange }

type ClassNode = Node<
  {
    label: string
    deprecated: boolean
    /** A comparison's changed attributes of the class, listed on it; empty or unset lists none. */
    attributes?: AttributeChange[]
  } & Emphasis &
    MapChangeData,
  'class'
>
/** `focused`: in the selection's focus, so its label shows at any zoom. */
type PatternEdge = Edge<
  { relation: string; route: LinkRoute; deprecated: boolean; focused: boolean } & Emphasis & MapChangeData,
  'pattern'
>
type SubclassEdge = Edge<MapChangeData, 'subclass'>

const NODE_TYPES = { class: ClassNodeView }
const EDGE_TYPES = { pattern: PatternEdgeView, subclass: SubclassEdgeView }

/** The hollow triangle at the superclass end of a subclass link (see `SubclassArrowhead`). */
const SUBCLASS_ARROWHEAD = 'ontology-map-subclass-arrowhead'

/** Fit-to-view never zooms out so far that link labels can no longer be read. */
const FIT_VIEW_OPTIONS = { minZoom: READABLE_ZOOM }

/** The dash of a removed link: a ghost of where it used to be. */
const REMOVED_DASH = '6 4'

/** How one change kind is drawn on every mark. */
interface ChangeStyle {
  /** A class's box, and the parts of it its severity colours. */
  node: string
  nodeSeverity: (keyof typeof SEVERITY)[]
  /** A link: dashed as a ghost, emphasized (thicker, its label bold), or muted. */
  dashed: boolean
  emphasized: boolean
  muted: boolean
  /** Its label outlined in its severity's colour, as a modified class is ringed. */
  outlined: boolean
  /** A small neutral dot beside its label, in no severity's colour. */
  dot: boolean
  /** The legend's swatch. */
  swatch: string
}

/**
 * Change kind's channel, mark style: added solid, removed a dashed ghost, modified ringed,
 * documentation-only a neutral dot on an otherwise plain mark, unchanged muted.
 */
const CHANGE_STYLE: Record<MapChangeKind, ChangeStyle> = {
  added: {
    node: 'border-2 font-semibold',
    nodeSeverity: ['border', 'fill'],
    dashed: false,
    emphasized: true,
    muted: false,
    outlined: false,
    dot: false,
    swatch: 'border-2 border-foreground bg-foreground/15',
  },
  removed: {
    node: 'border-2 border-dashed bg-transparent text-muted-foreground shadow-none',
    nodeSeverity: ['border'],
    dashed: true,
    emphasized: false,
    muted: false,
    outlined: false,
    dot: false,
    swatch: 'border-2 border-dashed border-foreground',
  },
  modified: {
    node: 'ring-2 ring-offset-2 ring-offset-background',
    nodeSeverity: ['ring'],
    dashed: false,
    emphasized: false,
    muted: false,
    outlined: true,
    dot: false,
    swatch: 'border ring-2 ring-foreground ring-offset-1 ring-offset-card',
  },
  // Nearly unchanged: no severity hue and no emphasis, only the dot.
  'documentation-only': {
    node: 'text-muted-foreground shadow-none',
    nodeSeverity: [],
    dashed: false,
    emphasized: false,
    muted: false,
    outlined: false,
    dot: true,
    swatch: 'flex items-center justify-center border bg-card',
  },
  unchanged: {
    node: 'bg-muted text-muted-foreground shadow-none',
    nodeSeverity: [],
    dashed: false,
    emphasized: false,
    muted: true,
    outlined: false,
    dot: false,
    swatch: 'border bg-muted',
  },
}

/** A documentation-only change's mark: small, round and neutral. */
function DocumentationDot({ className }: { className?: string }) {
  return (
    <span
      aria-hidden
      data-documentation-dot
      className={cn('inline-block size-1.5 shrink-0 rounded-full bg-muted-foreground', className)}
    />
  )
}

/** How `change` is drawn, or nothing outside a comparison. */
const changeStyle = (change?: MapChange): Partial<ChangeStyle> => (change ? CHANGE_STYLE[change.kind] : {})

type OntologyMapProps = { query?: string } & (
  | { ontology: Ontology; comparison?: never }
  | { comparison: OntologyComparison; ontology?: never }
)

/**
 * An Ontology as a node-link Map: classes as nodes, Patterns as links named by relation.
 * Selecting a class or link focuses its neighbourhood and opens its details; the selection
 * is the page's `?select=` (`useConceptSelection`), shared with the Table, and the Map
 * opens centred on it. `query`, the Concept search, highlights the Concepts it names and
 * lists its results beside the Map, where picking one selects it and centres the Map on it.
 *
 * Given a `comparison` instead, it draws both versions superimposed: change kind as mark
 * style (added solid, removed a dashed ghost, modified ringed, unchanged muted), severity
 * in the Diff colours, and a selection's Diff changes in its details.
 */
export function OntologyMap({ ontology: single, comparison, query = '' }: OntologyMapProps) {
  const ontology = comparison?.ontology ?? single!
  const map = useMemo(() => comparison?.map ?? ontologyMap(ontology), [comparison, ontology])
  const [filters, setFilters] = useState<MapFilters>({ hideDeprecated: false, hideSubclassLinks: false })
  const shown = useMemo(() => filterOntologyMap(map, filters), [map, filters])
  const [selected, setSelection] = useConceptSelection()
  // What the change summary points at: its focus shows, without selecting it.
  const [preview, setPreview] = useState<MapSelection | null>(null)
  // Focus is over what is shown, so a selection a filter hides is no selection. Hiding
  // subclass links only declutters: a path through an inherited Pattern still counts.
  const reachable = useMemo(
    () => (filters.hideSubclassLinks ? filterOntologyMap(map, { ...filters, hideSubclassLinks: false }) : shown),
    [map, filters, shown],
  )
  /**
   * What selecting `concept` selects on the Map: a class, or a relation as one of its
   * shown links, in a comparison its first changed one as the change summary has it;
   * null when none is shown.
   */
  const selectionFor = useCallback(
    (concept: ConceptSelection | null): MapSelection | null =>
      concept?.kind === 'relation'
        ? relationSelection(shown.links, concept.label, (l) => comparison !== undefined && linkChanged(comparison, l))
        : concept,
    [shown, comparison],
  )
  const selection = useMemo(() => selectionFor(selected), [selectionFor, selected])
  const selectedFocus = useMemo(() => focusOf(reachable, selection), [reachable, selection])
  const focus = useMemo(
    () => (preview ? focusOf(reachable, preview) : selectedFocus),
    [preview, reachable, selectedFocus],
  )
  const paths = useMemo(
    () =>
      selectedFocus && selection?.kind === 'path' ? shortestPaths(reachable, selection.from, selection.to) : null,
    [selectedFocus, reachable, selection],
  )
  const matches = useMemo(() => searchMap(ontology, query), [ontology, query])
  const results = useMemo(() => searchOntology(ontology, query), [ontology, query])
  // The selection the Map opened on or a search result picked (as a `?select=` value),
  // which the Map stays centred on while it lasts.
  const [located, setLocated] = useState(() => (selected ? formatSelection(selected) : null))
  /** What picking `result` selects; null when it is not shown. */
  const pick = ({ kind, label }: ClassOrRelation): ConceptSelection | null => {
    if (kind === 'relation') return selectionFor({ kind, label }) && { kind, label }
    return shown.nodes.some((n) => n.label === label) ? { kind, label } : null
  }
  const details = useMemo(
    () => (selectedFocus ? detailsOf(ontology, selection) : null),
    [selectedFocus, ontology, selection],
  )

  useEffect(() => {
    if (!selection) return
    const clear = (e: KeyboardEvent) => e.key === 'Escape' && setSelection(null)
    document.addEventListener('keydown', clear)
    return () => document.removeEventListener('keydown', clear)
  }, [selection, setSelection])
  // A comparison's changed classes grow to list their changed attributes.
  const sizes = useMemo(() => classSizes(comparison?.changes.attributes), [comparison])
  // The whole Map is laid out, and filters only hide, so nothing moves when one changes.
  const layout = useQuery({
    queryKey: ['ontology-map-layout', map, sizes],
    queryFn: () => layoutOntologyMap(map, sizes),
    staleTime: Infinity,
  })

  const elements = useMemo(() => {
    if (!layout.data) return null
    const positions = layout.data
    const faded = (key: string, focused?: Set<string>, matched?: Set<string>) =>
      focused ? !focused.has(key) : matched ? !matched.has(key) : false
    const classEmphasis = (label: string): Emphasis => ({
      // The selected class, or either end of a path.
      selected:
        selection?.kind === 'class'
          ? selection.label === label
          : selection?.kind === 'path' && (selection.from === label || selection.to === label),
      match: matches?.classes.has(label) ?? false,
      faded: faded(label, focus?.classes, matches?.classes),
    })
    const linkEmphasis = (id: string): Emphasis => ({
      // The selected link, or any link along a path.
      selected:
        selection?.kind === 'link'
          ? selection.id === id
          : selection?.kind === 'path' && (focus?.links.has(id) ?? false),
      match: matches?.links.has(id) ?? false,
      faded: faded(id, focus?.links, matches?.links),
    })
    const nodes: ClassNode[] = shown.nodes.map((n) => ({
      id: n.label,
      type: 'class',
      position: positions[n.label],
      data: {
        label: n.label,
        deprecated: n.deprecated,
        change: comparison?.changes.classes[n.label],
        attributes: comparison?.changes.attributes[n.label],
        ...classEmphasis(n.label),
      },
      ariaLabel: n.label,
      ...(sizes[n.label] ?? NODE_SIZE),
    }))
    const patternEdges: PatternEdge[] = shown.links.map((l) => ({
      id: l.id,
      type: 'pattern',
      source: l.source,
      target: l.target,
      data: {
        relation: l.relation,
        route: l.route,
        deprecated: l.deprecated,
        focused: focus?.links.has(l.id) ?? false,
        change: comparison?.changes.links[l.id],
        ...linkEmphasis(l.id),
      },
      ariaLabel: l.id,
      className: cn(l.deprecated && 'opacity-50'),
      markerEnd: {
        type: MarkerType.ArrowClosed,
        color: severityStroke(comparison?.changes.links[l.id]?.severity ?? null) ?? 'var(--muted-foreground)',
      },
    }))
    const subclassEdges: SubclassEdge[] = shown.subclassLinks.map((l) => ({
      id: l.id,
      type: 'subclass',
      source: l.child,
      target: l.parent,
      data: { change: comparison?.changes.subclassLinks[l.id] },
      ariaLabel: l.id,
      // A subclass link fades with either of its classes.
      className: cn(
        (classEmphasis(l.child).faded || classEmphasis(l.parent).faded) && 'opacity-20',
      ),
      markerEnd: SUBCLASS_ARROWHEAD,
    }))
    return { nodes, edges: [...subclassEdges, ...patternEdges] }
  }, [layout.data, sizes, shown, focus, matches, selection, comparison])

  const centre = useMemo(
    () => (layout.data ? centreOf(map, layout.data, sizes, locatedSelection(located, selected, selection)) : null),
    [layout.data, sizes, located, selected, selection, map],
  )

  if (layout.error) return <ErrorAlert error={layout.error} title="The Map could not be laid out" />
  if (!elements) return <Skeleton className={cn(MAP_HEIGHT, 'w-full')} />
  return (
    <div className={cn('flex overflow-hidden rounded-md border', MAP_HEIGHT)}>
      {comparison && (
        <MapChangeSummary
          comparison={comparison}
          selection={selection}
          onPreview={setPreview}
          onSelect={setSelection}
        />
      )}
      {query.trim() !== '' && (
        <MapSearchResults
          query={query}
          results={results}
          canPick={(r) => pick(r) !== null}
          onPick={(r) => {
            const picked = pick(r)
            setSelection(picked)
            setLocated(picked && formatSelection(picked))
          }}
        />
      )}
      <ReactFlow
        aria-label="Ontology Map"
        className="min-w-0 flex-1"
        nodes={elements.nodes}
        edges={elements.edges}
        nodeTypes={NODE_TYPES}
        edgeTypes={EDGE_TYPES}
        nodesDraggable={false}
        nodesConnectable={false}
        // The Map keeps its own selection (focus and details), not React Flow's.
        elementsSelectable={false}
        // Shift-clicking a second class asks for the shortest paths from the first.
        onNodeClick={(event, node) =>
          setSelection(
            event.shiftKey && selection?.kind === 'class' && selection.label !== node.id
              ? { kind: 'path', from: selection.label, to: node.id }
              : { kind: 'class', label: node.id },
          )
        }
        onEdgeClick={(_, edge) => edge.type === 'pattern' && setSelection({ kind: 'link', id: edge.id })}
        onPaneClick={() => setSelection(null)}
        minZoom={0.2}
        // Opening on a selection centres on it instead.
        fitView={located === null}
        fitViewOptions={FIT_VIEW_OPTIONS}
      >
        <Controls showInteractive={false} fitViewOptions={FIT_VIEW_OPTIONS} />
        <Panel position="top-right" className="flex gap-4 rounded-md border bg-card px-3 py-2 text-sm shadow-xs">
          <FilterSwitch
            id="map-hide-deprecated"
            label="Hide deprecated"
            checked={filters.hideDeprecated}
            onCheckedChange={(hideDeprecated) => setFilters({ ...filters, hideDeprecated })}
          />
          <FilterSwitch
            id="map-hide-subclass-links"
            label="Hide subclass links"
            checked={filters.hideSubclassLinks}
            onCheckedChange={(hideSubclassLinks) => setFilters({ ...filters, hideSubclassLinks })}
          />
        </Panel>
        {comparison && <ComparisonLegend />}
        <CentreOn point={centre} />
      </ReactFlow>
      {details && (
        <MapDetailsPanel details={details} onClose={() => setSelection(null)}>
          {comparison && <ChangeDetails comparison={comparison} selection={selection} />}
          {details.kind === 'class' && (
            <p className="text-xs text-muted-foreground">Shift-click another class for the shortest path to it.</p>
          )}
        </MapDetailsPanel>
      )}
      {paths && selection?.kind === 'path' && (
        <MapPathPanel from={selection.from} to={selection.to} paths={paths} onClose={() => setSelection(null)} />
      )}
      <SubclassArrowhead />
    </div>
  )
}

/**
 * Centres the Map on `point` (at a readable zoom at least), and again whenever the canvas
 * resizes, as it does when the details panel opens.
 */
function CentreOn({ point }: { point: Point | null }) {
  const { setCenter, getZoom } = useReactFlow()
  const width = useStore((s) => s.width)
  const height = useStore((s) => s.height)
  useEffect(() => {
    if (point) void setCenter(point.x, point.y, { zoom: Math.max(getZoom(), 1), duration: 200 })
  }, [point, width, height, setCenter, getZoom])
  return null
}

/** A comparison's details section: the Ontology Diff's changes behind the selection. */
function ChangeDetails({
  comparison,
  selection,
}: {
  comparison: OntologyComparison
  selection: MapSelection | null
}) {
  const changes = changesOf(comparison, selection)
  return (
    <section className="space-y-1">
      <h4 className="text-xs font-semibold">Changes</h4>
      {changes.length === 0 ? (
        <p className="text-xs text-muted-foreground">No changes.</p>
      ) : (
        <ul aria-label="Changes" className="space-y-2">
          {changes.map((c) => (
            <li key={`${c.concept}:${c.detail}`} className="space-y-1">
              <div className="flex items-center gap-2">
                <ChangeLevelBadge level={levelOf(comparison, c)} />
                <span className="text-xs text-muted-foreground">{c.kind}</span>
              </div>
              <div className="text-xs">{c.detail}</div>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}

/** A comparison's key to change kind (mark style) and severity (the Diff colours). */
function ComparisonLegend() {
  return (
    <Panel
      position="top-left"
      aria-label="Legend"
      className="flex max-w-[45%] flex-wrap items-center gap-x-3 gap-y-1 rounded-md border bg-card px-3 py-2 text-xs shadow-xs"
    >
      {Object.entries(CHANGE_STYLE).map(([kind, { swatch, dot }]) => (
        <span key={kind} className="flex items-center gap-1">
          <span aria-hidden className={cn('inline-block h-3 w-5 rounded-sm', swatch)}>
            {dot && <DocumentationDot />}
          </span>
          {kind}
        </span>
      ))}
      {CLASSIFICATIONS.map((s) => (
        <ClassificationBadge key={s} classification={s} />
      ))}
    </Panel>
  )
}

function FilterSwitch({
  id,
  label,
  checked,
  onCheckedChange,
}: {
  id: string
  label: string
  checked: boolean
  onCheckedChange: (checked: boolean) => void
}) {
  return (
    <div className="flex items-center gap-2">
      <Switch id={id} size="sm" checked={checked} onCheckedChange={onCheckedChange} />
      <Label htmlFor={id}>{label}</Label>
    </div>
  )
}

/** The marker subclass links end in: a hollow triangle, so they never read as a relation. */
function SubclassArrowhead() {
  return (
    <svg className="absolute size-0" aria-hidden>
      <defs>
        <marker
          id={SUBCLASS_ARROWHEAD}
          viewBox="-10 -10 20 20"
          markerUnits="userSpaceOnUse"
          markerWidth="16"
          markerHeight="16"
          orient="auto-start-reverse"
        >
          <polygon points="-8,-5 0,0 -8,5" fill="var(--background)" stroke="var(--muted-foreground)" />
        </marker>
      </defs>
    </svg>
  )
}

function ClassNodeView({ data }: NodeProps<ClassNode>) {
  const severity = data.change?.severity
  const style = changeStyle(data.change)
  return (
    <div
      data-class
      data-selected={data.selected || undefined}
      data-match={data.match || undefined}
      data-faded={data.faded || undefined}
      data-change={data.change?.kind}
      data-severity={severity ?? undefined}
      className={cn(
        'flex size-full cursor-pointer flex-col items-center justify-center rounded-md border bg-card px-2 text-sm font-medium text-card-foreground shadow-xs transition-opacity',
        // Deprecated: faded, with a struck-through label.
        data.deprecated && 'opacity-50',
        // Change kind as mark style, severity in the Diff colours.
        style.node,
        severity && style.nodeSeverity?.map((part) => SEVERITY[part][severity]),
        // Search matches get a ring in the primary colour: diff-* hues are reserved for severity.
        data.match && 'ring-2 ring-primary ring-offset-2 ring-offset-background',
        data.selected && 'border-2 border-foreground',
        data.faded && 'opacity-30',
      )}
    >
      <span
        className={cn('flex max-w-full shrink-0 items-center truncate', data.deprecated && 'line-through')}
        style={{ height: NODE_SIZE.height - 2 }}
      >
        {data.label}
        {style.dot && <DocumentationDot className="ml-1.5" />}
      </span>
      {data.attributes && data.attributes.length > 0 && <ChangedAttributes attributes={data.attributes} />}
      {/* React Flow attaches links to handles; links are drawn centre to centre, so these stay hidden. */}
      <Handle type="target" position={Position.Top} isConnectable={false} className="invisible" />
      <Handle type="source" position={Position.Bottom} isConnectable={false} className="invisible" />
    </div>
  )
}

/** A comparison's changed attributes of one class, one line each, diff-style, in their severity. */
function ChangedAttributes({ attributes }: { attributes: AttributeChange[] }) {
  return (
    <ul
      aria-label="Changed attributes"
      className="w-full pb-1 font-mono font-normal"
      style={{ fontSize: MONOSPACE_FONT_SIZE }}
    >
      {attributes.map((a) => (
        <li
          key={a.name}
          data-change={a.kind}
          data-severity={a.severity}
          title={attributeLine(a)}
          className={cn('truncate text-left', SEVERITY.text[a.severity])}
          style={{ height: ATTRIBUTE_LINE_HEIGHT, lineHeight: `${ATTRIBUTE_LINE_HEIGHT}px` }}
        >
          {ATTRIBUTE_MARKER[a.kind]} {a.name}
          {a.details.length > 0 && <span className="text-muted-foreground"> {a.details.join('; ')}</span>}
        </li>
      ))}
    </ul>
  )
}

function PatternEdgeView({ id, source, target, data, markerEnd }: EdgeProps<PatternEdge>) {
  const from = useInternalNode(source)
  const to = useInternalNode(target)
  // Re-rendered only when the label shows or hides, not on every step of a zoom.
  const labelVisible = useStore((s) => labelShown(s.transform[2], { focused: data?.focused ?? false, change: data?.change }))
  if (!from || !to || !data) return null
  const { path, label } = linkShape(data, box(from), box(to))

  const severity = data.change?.severity ?? null
  const style = changeStyle(data.change)
  const stroke = data.selected ? 'var(--foreground)' : data.match ? 'var(--primary)' : (severityStroke(severity) ?? undefined)
  const emphasized = data.selected || data.match || style.emphasized

  return (
    <>
      <BaseEdge
        id={id}
        path={path}
        markerEnd={markerEnd}
        interactionWidth={16}
        data-change={data.change?.kind}
        data-severity={severity ?? undefined}
        style={{
          stroke,
          strokeWidth: emphasized ? 2 : undefined,
          strokeDasharray: style.dashed ? REMOVED_DASH : undefined,
          opacity: data.faded ? 0.2 : style.muted ? 0.4 : undefined,
          cursor: 'pointer',
        }}
      />
      {labelVisible && (
        // The top layer, above every node and link. The pill stays solid, so a link or a
        // faded item never shows through; only its text fades.
        <ViewportPortal>
          {/* Relation names are text only: hue is reserved for severity. */}
          <div
            data-link-label
            className={cn(
              'nodrag nopan pointer-events-none absolute flex items-center justify-center whitespace-nowrap rounded-full border bg-background font-mono text-muted-foreground shadow-xs',
              style.outlined && severity && SEVERITY.border[severity],
              (emphasized || style.outlined) && 'font-semibold text-foreground',
            )}
            style={{ left: label.x, top: label.y, width: label.width, height: label.height, fontSize: MONOSPACE_FONT_SIZE }}
          >
            <span
              className={cn(
                data.deprecated && 'line-through opacity-50',
                style.muted && 'opacity-60',
                data.faded && 'opacity-30',
              )}
            >
              {data.relation}
            </span>
            {/* On the pill's corner, so the label keeps the size the layout made room for. */}
            {style.dot && <DocumentationDot className="absolute -top-0.5 -right-0.5" />}
          </div>
        </ViewportPortal>
      )}
    </>
  )
}

/** A subclass link: thin, grey and straight, from the subclass to its superclass. */
function SubclassEdgeView({ id, source, target, markerEnd, data }: EdgeProps<SubclassEdge>) {
  const from = useInternalNode(source)
  const to = useInternalNode(target)
  if (!from || !to) return null
  const path = straightPath(box(from), box(to))
  const style = changeStyle(data?.change)
  return (
    <BaseEdge
      id={id}
      path={path}
      markerEnd={markerEnd}
      style={{
        // Thin whatever its change, so it never reads as a relation.
        stroke: severityStroke(data?.change?.severity ?? null) ?? 'var(--muted-foreground)',
        strokeOpacity: style.muted ? 0.3 : 0.6,
        strokeWidth: 1,
        strokeDasharray: style.dashed ? REMOVED_DASH : undefined,
      }}
    />
  )
}

/** A drawn class node's box, at its size on the Map, which a comparison may grow. */
const box = (node: InternalNode): Box => ({
  ...node.internals.positionAbsolute,
  width: node.width ?? NODE_SIZE.width,
  height: node.height ?? NODE_SIZE.height,
})
