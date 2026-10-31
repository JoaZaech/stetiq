import '@xyflow/react/dist/style.css'
import { useEffect, useMemo, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
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
import { CLASSIFICATION_LABEL, type OntologyChange } from '@/api/ontology-diff'
import type { Ontology } from '@/api/ontology-versions'
import { ErrorAlert } from '@/components/ErrorAlert'
import { ClassificationBadge } from '@/components/OntologyDiff'
import { Label } from '@/components/ui/label'
import { Skeleton } from '@/components/ui/skeleton'
import { Switch } from '@/components/ui/switch'
import { cn } from '@/lib/utils'
import { formatSelection, useConceptSelection } from '../concept-selection'
import { MapChangeSummary, MapChangesRail } from '../comparison/MapChangeSummary'
import { CosmeticDot } from '@/components/SeveritySwatch'
import { MapDetailsPanel } from './MapDetailsPanel'
import { MAP_HEIGHT } from '../map-view'
import { MapPathPanel } from './MapPathPanel'
import { MapSearchResults } from './MapSearchResults'
import type { MapPanelNav } from './MapSidePanel'
import type { LinkRoute } from './ontology-map'
import {
  type AttributeChange,
  descriptionChangeOf,
  type MapChange,
  type MapChangeKind,
  type OntologyComparison,
} from '../comparison/ontology-map-comparison'
import { DescriptionDiff } from '../comparison/DescriptionDiff'
import { centreOf, FIRST_VIEW_MIN_ZOOM } from './ontology-map-centre'
import { layoutOntologyMap, type Point } from './ontology-map-layout'
import { labelShown, linkShape, straightPath, type Box } from './ontology-map-links'
import {
  ATTRIBUTE_LINE_HEIGHT,
  ATTRIBUTE_MARKER,
  attributeLine,
  CLASS_NAME_FONT_SIZE,
  classSizes,
  MONOSPACE_FONT_SIZE,
  NODE_SIZE,
} from './ontology-map-sizes'
import {
  canPick,
  createDrawnMapOf,
  initialMapState,
  respondTo,
  type Emphasis,
  type LinkEmphasis,
  type MapGesture,
  type MapPanelBack,
} from './ontology-map-view'
import { SEVERITY, severityStroke } from '@/components/severity-style'

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
type PatternEdge = Edge<
  { relation: string; route: LinkRoute; deprecated: boolean } & LinkEmphasis & MapChangeData,
  'pattern'
>
type SubclassEdge = Edge<MapChangeData, 'subclass'>

const NODE_TYPES = { class: ClassNodeView }
const EDGE_TYPES = { pattern: PatternEdgeView, subclass: SubclassEdgeView }

/** The hollow triangle at the superclass end of a subclass link (see `SubclassArrowhead`). */
const SUBCLASS_ARROWHEAD = 'ontology-map-subclass-arrowhead'

/**
 * How far the change-kind key sits from the canvas's left edge: past the zoom controls
 * (React Flow's 15px margin and 26px buttons), with a gap.
 */
const KEY_LEFT = 15 + 26 + 8

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
  /** Its swatch in the change-kind key; cosmetic has none, its key being the panel's documentation-only dot. */
  swatch?: string
}

/**
 * Change kind's channel, mark style: added solid, removed a dashed ghost, modified ringed,
 * cosmetic (only cosmetic changes) a neutral dot on an otherwise plain mark,
 * unchanged muted.
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
  cosmetic: {
    node: 'text-muted-foreground shadow-none',
    nodeSeverity: [],
    dashed: false,
    emphasized: false,
    muted: false,
    outlined: false,
    dot: true,
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

/** What a panel's back link says, by where it goes back to. */
const BACK_LABEL: Record<MapPanelBack, string> = { changes: 'All changes', results: 'Results' }

/** How `change` is drawn, or nothing outside a comparison. */
const changeStyle = (change?: MapChange): Partial<ChangeStyle> => (change ? CHANGE_STYLE[change.kind] : {})

/** A change kind as the UI names it (the change-kind key, `data-change`): cosmetic is "documentation-only", as its class is. */
const changeKindLabel = (kind: MapChangeKind): string => (kind === 'cosmetic' ? CLASSIFICATION_LABEL.cosmetic : kind)

type OntologyMapProps = {
  query?: string
  /** Where its filters go, in the page's header row (`useMapViewControls`); none shows none. */
  filtersIn?: HTMLElement | null
} & (
  | { ontology: Ontology; comparison?: never }
  | { comparison: OntologyComparison; ontology?: never }
)

/**
 * An Ontology as a node-link Map: classes as nodes, Patterns as links named by relation.
 * Selecting a class or link focuses its neighbourhood and opens its details; the selection
 * is the page's `?select=` (`useConceptSelection`), shared with the Table, and the Map
 * opens centred on it. `query`, the Concept search, highlights the Concepts it names and
 * lists its results, where picking one selects it and centres the Map on it.
 *
 * Given a `comparison` instead, it draws both versions superimposed: change kind as mark
 * style (added solid, removed a dashed ghost, modified ringed, unchanged muted), severity
 * in the Diff colours, and a selection's Diff changes in its details.
 *
 * Details, paths, results and a comparison's change summary share one panel on the
 * Map's right (`DrawnMap.panel`); a comparison's collapses to a rail of its counts.
 */
export function OntologyMap({ ontology, comparison, query = '', filtersIn }: OntologyMapProps) {
  const [selected, setSelection] = useConceptSelection()
  const drawnMapOf = useMemo(() => createDrawnMapOf(), [])
  const [state, setState] = useState(() => initialMapState(selected))
  const [collapsed, setCollapsed] = useState(false)
  // A new selection or search opens a collapsed panel, so its details, path or results show.
  const shownFor = `${selected ? formatSelection(selected) : ''} ${query.trim()}`
  const [lastShownFor, setLastShownFor] = useState(shownFor)
  if (shownFor !== lastShownFor) {
    setLastShownFor(shownFor)
    if (shownFor.trim() !== '') setCollapsed(false)
  }
  const view = drawnMapOf(comparison ? { comparison, selected, query } : { ontology: ontology!, selected, query }, state)
  const { map, shown, selection, details, paths, results, classes, links, subclassLinks, panel } = view
  /** Answers `gesture` as the view says: its next state, and the page's next selection. */
  const respond = (gesture: MapGesture) => {
    const { state: next, select } = respondTo(view, gesture)
    if (next !== state) setState(next)
    if (select !== undefined) setSelection(select)
  }
  // The Escape listener, kept for the Map's life, answers with the latest view.
  const respondLatest = useRef(respond)
  useEffect(() => {
    respondLatest.current = respond
  })
  useEffect(() => {
    const escape = (e: KeyboardEvent) => e.key === 'Escape' && respondLatest.current({ kind: 'escape' })
    document.addEventListener('keydown', escape)
    return () => document.removeEventListener('keydown', escape)
  }, [])
  // Each class grows to fit its name and, in a comparison, to list its changed attributes.
  const sizes = useMemo(
    () =>
      classSizes(
        map.nodes.map((n) => n.label),
        comparison?.changes.attributes,
      ),
    [map, comparison],
  )
  // The whole Map is laid out, and filters only hide, so nothing moves when one changes.
  const layout = useQuery({
    queryKey: ['ontology-map-layout', map, sizes],
    queryFn: () => layoutOntologyMap(map, sizes),
    staleTime: Infinity,
  })

  const elements = useMemo(() => {
    if (!layout.data) return null
    const positions = layout.data
    const nodes: ClassNode[] = shown.nodes.map((n) => ({
      id: n.label,
      type: 'class',
      position: positions[n.label],
      data: {
        label: n.label,
        deprecated: n.deprecated,
        change: comparison?.changes.classes[n.label],
        attributes: comparison?.changes.attributes[n.label],
        ...classes[n.label],
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
        change: comparison?.changes.links[l.id],
        ...links[l.id],
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
      className: cn(subclassLinks[l.id].faded && 'opacity-20'),
      markerEnd: SUBCLASS_ARROWHEAD,
    }))
    return { nodes, edges: [...subclassEdges, ...patternEdges] }
  }, [layout.data, sizes, shown, classes, links, subclassLinks, comparison])

  // The Map opens on what `fitTo` names (a comparison's changes), else on all of it, never
  // zooming out so far that class names can no longer be read. Fit view frames it all.
  const openingFit = useMemo(
    () => ({ minZoom: FIRST_VIEW_MIN_ZOOM, nodes: view.fitTo?.map((id) => ({ id })) }),
    [view.fitTo],
  )

  const centre = useMemo(
    () => (layout.data ? centreOf(map, layout.data, sizes, view.centreOn) : null),
    [layout.data, sizes, map, view.centreOn],
  )

  // The summary and results only collapse; a selection's panel goes back to them, or
  // closes when there is none. Both clear the selection, so the panel shows what it came from.
  const listNav: MapPanelNav = { onCollapse: comparison && (() => setCollapsed(true)) }
  const clear = () => respond({ kind: 'clear' })
  const selectionNav: MapPanelNav = {
    ...listNav,
    ...(panel && 'back' in panel && panel.back ? { back: { label: BACK_LABEL[panel.back], onBack: clear } } : { onClose: clear }),
  }

  if (layout.error) return <ErrorAlert error={layout.error} title="The Map could not be laid out" />
  if (!elements) return <Skeleton className={cn(MAP_HEIGHT, 'w-full')} />
  return (
    <div className={cn('flex overflow-hidden rounded-md border', MAP_HEIGHT)}>
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
        onNodeClick={(event, node) => respond({ kind: 'click-class', label: node.id, shift: event.shiftKey })}
        onEdgeClick={(_, edge) => edge.type === 'pattern' && respond({ kind: 'click-link', id: edge.id })}
        onPaneClick={() => respond({ kind: 'clear' })}
        minZoom={0.2}
        fitView={view.fitView}
        fitViewOptions={openingFit}
      >
        <Controls showInteractive={false} />
        {comparison && <ChangeKindKey />}
        <CentreOn point={centre} />
      </ReactFlow>
      {comparison && collapsed ? (
        <MapChangesRail comparison={comparison} onExpand={() => setCollapsed(false)} />
      ) : (
        <>
          {panel?.kind === 'summary' && comparison && (
            <MapChangeSummary
              comparison={comparison}
              shown={shown.links}
              returnTo={panel.returnTo}
              onPreview={(preview) => respond({ kind: 'preview', selection: preview })}
              onSelect={(concept) => respond({ kind: 'select', concept })}
              nav={listNav}
            />
          )}
          {panel?.kind === 'results' && (
            <MapSearchResults
              query={query}
              results={results}
              canPick={(r) => canPick(view, r)}
              onPick={(r) => respond({ kind: 'pick', result: r })}
              nav={listNav}
            />
          )}
          {panel?.kind === 'details' && details && (
            <MapDetailsPanel details={details} nav={selectionNav}>
              {view.changes && comparison && <ChangeDetails comparison={comparison} changes={view.changes} />}
              {details.kind === 'class' && (
                <p className="text-xs text-muted-foreground">Shift-click another class for the shortest path to it.</p>
              )}
            </MapDetailsPanel>
          )}
          {panel?.kind === 'path' && paths && selection?.kind === 'path' && (
            <MapPathPanel from={selection.from} to={selection.to} paths={paths} nav={selectionNav} />
          )}
        </>
      )}
      <SubclassArrowhead />
      {/* Off the canvas, in the page's header row, so nothing overlays the top of the Map. */}
      {filtersIn &&
        createPortal(
          <>
            <FilterSwitch
              id="map-hide-deprecated"
              label="Hide deprecated"
              checked={state.filters.hideDeprecated}
              onCheckedChange={(hideDeprecated) => respond({ kind: 'filter', filters: { hideDeprecated } })}
            />
            <FilterSwitch
              id="map-hide-subclass-links"
              label="Hide subclass links"
              checked={state.filters.hideSubclassLinks}
              onCheckedChange={(hideSubclassLinks) => respond({ kind: 'filter', filters: { hideSubclassLinks } })}
            />
          </>,
          filtersIn,
        )}
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

/**
 * A comparison's details section: the Ontology Diff's changes behind the selection, a
 * documentation-only one with its description before and after.
 */
function ChangeDetails({ comparison, changes }: { comparison: OntologyComparison; changes: OntologyChange[] }) {
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
                <ClassificationBadge classification={c.classification} />
                <span className="text-xs text-muted-foreground">{c.kind}</span>
              </div>
              <div className="text-xs">{c.detail}</div>
              <ChangedDescription comparison={comparison} change={c} />
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}

/** A documentation-only change's description before and after; nothing for any other change. */
function ChangedDescription({ comparison, change }: { comparison: OntologyComparison; change: OntologyChange }) {
  const description = descriptionChangeOf(comparison, change)
  return description && <DescriptionDiff change={description} />
}

/**
 * A comparison's key to change kind (mark style), one row at the bottom-left beside the
 * zoom controls. Severity's key is the panel's headline counts, not this.
 */
function ChangeKindKey() {
  return (
    <Panel position="bottom-left" role="region" aria-label="Change kind" style={{ marginLeft: KEY_LEFT }}>
      <ul className="flex items-center gap-3 rounded-md border bg-card px-2 py-1 text-xs whitespace-nowrap shadow-xs">
        {(Object.entries(CHANGE_STYLE) as [MapChangeKind, ChangeStyle][]).map(
          ([kind, { swatch }]) =>
            swatch && (
              <li key={kind} className="flex items-center gap-1.5">
                <span aria-hidden className={cn('inline-block h-3 w-5 rounded-sm', swatch)} />
                {changeKindLabel(kind)}
              </li>
            ),
        )}
      </ul>
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
      data-context={data.context || undefined}
      data-faded={data.faded || undefined}
      data-change={data.change && changeKindLabel(data.change.kind)}
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
        // Changed but out of focus: readable as context, its severity still drawn.
        data.context && 'opacity-60',
        data.faded && 'opacity-30',
      )}
    >
      <span
        className={cn('flex shrink-0 items-center font-mono whitespace-nowrap', data.deprecated && 'line-through')}
        style={{ height: NODE_SIZE.height - 2, fontSize: CLASS_NAME_FONT_SIZE }}
      >
        {data.label}
        {style.dot && <CosmeticDot className="ml-1.5" />}
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
        data-change={data.change && changeKindLabel(data.change.kind)}
        data-severity={severity ?? undefined}
        style={{
          stroke,
          strokeWidth: emphasized ? 2 : undefined,
          strokeDasharray: style.dashed ? REMOVED_DASH : undefined,
          opacity: data.faded ? 0.2 : data.context ? 0.6 : style.muted ? 0.4 : undefined,
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
                data.context && 'opacity-60',
                data.faded && 'opacity-30',
              )}
            >
              {data.relation}
            </span>
            {/* On the pill's corner, so the label keeps the size the layout made room for. */}
            {style.dot && <CosmeticDot className="absolute -top-0.5 -right-0.5" />}
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
