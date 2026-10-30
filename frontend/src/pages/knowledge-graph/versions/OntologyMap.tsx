import '@xyflow/react/dist/style.css'
import { useEffect, useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  BaseEdge,
  Controls,
  EdgeLabelRenderer,
  Handle,
  MarkerType,
  Position,
  ReactFlow,
  useInternalNode,
  type Edge,
  type EdgeProps,
  type Node,
  type NodeProps,
} from '@xyflow/react'
import type { Ontology } from '@/api/ontology-versions'
import { ErrorAlert } from '@/components/ErrorAlert'
import { Skeleton } from '@/components/ui/skeleton'
import { cn } from '@/lib/utils'
import { MapDetailsPanel } from './MapDetailsPanel'
import {
  detailsOf,
  focusOf,
  layoutOntologyMap,
  NODE_SIZE,
  ontologyMap,
  searchMap,
  type LinkRoute,
  type MapSelection,
  type Point,
} from './ontology-map'

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

type ClassNode = Node<{ label: string } & Emphasis, 'class'>
type PatternEdge = Edge<{ relation: string; route: LinkRoute } & Emphasis, 'pattern'>

const NODE_TYPES = { class: ClassNodeView }
const EDGE_TYPES = { pattern: PatternEdgeView }

/** Pixels between parallel links, per unit of a `line` route's bend. */
const BEND_SPACING = 48
/** How far the smallest self-loop reaches out of its class, and how much each further loop adds. */
const LOOP_REACH = 48
const LOOP_STEP = 24

/**
 * An Ontology as a node-link Map: classes as nodes, Patterns as links named by relation.
 * Selecting a class or link focuses its neighbourhood and opens its details; `query`, the
 * Concept search, highlights its matches.
 */
export function OntologyMap({ ontology, query = '' }: { ontology: Ontology; query?: string }) {
  const map = useMemo(() => ontologyMap(ontology), [ontology])
  const [selection, setSelection] = useState<MapSelection | null>(null)
  const focus = useMemo(() => focusOf(map, selection), [map, selection])
  const matches = useMemo(() => searchMap(ontology, query), [ontology, query])
  const details = useMemo(() => detailsOf(ontology, selection), [ontology, selection])

  useEffect(() => {
    if (!selection) return
    const clear = (e: KeyboardEvent) => e.key === 'Escape' && setSelection(null)
    document.addEventListener('keydown', clear)
    return () => document.removeEventListener('keydown', clear)
  }, [selection])
  const layout = useQuery({
    queryKey: ['ontology-map-layout', map],
    queryFn: () => layoutOntologyMap(map),
    staleTime: Infinity,
  })

  const elements = useMemo(() => {
    if (!layout.data) return null
    const positions = layout.data
    const emphasis = (kind: 'class' | 'link', key: string): Emphasis => {
      const focused = kind === 'class' ? focus?.classes : focus?.links
      const matched = kind === 'class' ? matches?.classes : matches?.links
      return {
        selected:
          (kind === 'class' && selection?.kind === 'class' && selection.label === key) ||
          (kind === 'link' && selection?.kind === 'link' && selection.id === key),
        match: matched?.has(key) ?? false,
        faded: focused ? !focused.has(key) : matched ? !matched.has(key) : false,
      }
    }
    const nodes: ClassNode[] = map.nodes.map((n) => ({
      id: n.label,
      type: 'class',
      position: positions[n.label],
      data: { label: n.label, ...emphasis('class', n.label) },
      ariaLabel: n.label,
      ...NODE_SIZE,
    }))
    const edges: PatternEdge[] = map.links.map((l) => ({
      id: l.id,
      type: 'pattern',
      source: l.source,
      target: l.target,
      data: { relation: l.relation, route: l.route, ...emphasis('link', l.id) },
      ariaLabel: l.id,
      markerEnd: { type: MarkerType.ArrowClosed, color: 'var(--muted-foreground)' },
    }))
    return { nodes, edges }
  }, [layout.data, map, focus, matches, selection])

  if (layout.error) return <ErrorAlert error={layout.error} title="The Map could not be laid out" />
  if (!elements) return <Skeleton className="h-[32rem] w-full" />
  return (
    <div className="flex h-[32rem] overflow-hidden rounded-md border">
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
        onNodeClick={(_, node) => setSelection({ kind: 'class', label: node.id })}
        onEdgeClick={(_, edge) => setSelection({ kind: 'link', id: edge.id })}
        onPaneClick={() => setSelection(null)}
        minZoom={0.2}
        fitView
      >
        <Controls showInteractive={false} />
      </ReactFlow>
      {details && <MapDetailsPanel details={details} onClose={() => setSelection(null)} />}
    </div>
  )
}

function ClassNodeView({ data }: NodeProps<ClassNode>) {
  return (
    <div
      data-class
      data-selected={data.selected || undefined}
      data-match={data.match || undefined}
      data-faded={data.faded || undefined}
      className={cn(
        'flex size-full cursor-pointer items-center justify-center rounded-md border bg-card px-2 text-sm font-medium text-card-foreground shadow-xs transition-opacity',
        // Search matches get a ring in the primary colour: diff-* hues are reserved for severity.
        data.match && 'ring-2 ring-primary ring-offset-2 ring-offset-background',
        data.selected && 'border-2 border-foreground',
        data.faded && 'opacity-30',
      )}
    >
      <span className="truncate">{data.label}</span>
      {/* React Flow attaches links to handles; links are drawn centre to centre, so these stay hidden. */}
      <Handle type="target" position={Position.Top} isConnectable={false} className="invisible" />
      <Handle type="source" position={Position.Bottom} isConnectable={false} className="invisible" />
    </div>
  )
}

function PatternEdgeView({ id, source, target, data, markerEnd }: EdgeProps<PatternEdge>) {
  const from = useInternalNode(source)
  const to = useInternalNode(target)
  if (!from || !to || !data) return null
  const a = center(from.internals.positionAbsolute)
  const b = center(to.internals.positionAbsolute)
  const { path, label, labelAlign } =
    data.route.kind === 'loop' ? loopPath(a, data.route.size) : linePath(a, b, data.route.bend)
  // A link's label is centred on it; a loop's sits just outside the arc.
  const anchor = labelAlign === 'start' ? 'translate(0, -50%)' : 'translate(-50%, -50%)'

  const stroke = data.selected ? 'var(--foreground)' : data.match ? 'var(--primary)' : undefined

  return (
    <>
      <BaseEdge
        id={id}
        path={path}
        markerEnd={markerEnd}
        interactionWidth={16}
        style={{
          stroke,
          strokeWidth: data.selected || data.match ? 2 : undefined,
          opacity: data.faded ? 0.2 : undefined,
          cursor: 'pointer',
        }}
      />
      <EdgeLabelRenderer>
        {/* Relation names are text only: hue is reserved for severity. */}
        <div
          className={cn(
            'nodrag nopan pointer-events-none absolute rounded-sm bg-background/90 px-1 font-mono text-[10px] text-muted-foreground',
            (data.selected || data.match) && 'font-semibold text-foreground',
            data.faded && 'opacity-30',
          )}
          style={{ transform: `translate(${label.x}px, ${label.y}px) ${anchor}` }}
        >
          {data.relation}
        </div>
      </EdgeLabelRenderer>
    </>
  )
}

const center = (topLeft: Point): Point => ({
  x: topLeft.x + NODE_SIZE.width / 2,
  y: topLeft.y + NODE_SIZE.height / 2,
})

/** Where the ray from a node's centre towards `toward` leaves the node's box. */
function boundary(c: Point, toward: Point): Point {
  const dx = toward.x - c.x
  const dy = toward.y - c.y
  if (dx === 0 && dy === 0) return c
  const scale = 1 / Math.max(Math.abs(dx) / (NODE_SIZE.width / 2), Math.abs(dy) / (NODE_SIZE.height / 2))
  return { x: c.x + dx * scale, y: c.y + dy * scale }
}

/** A quadratic curve between two classes, bent `bend` spacings to the left of a → b. */
function linePath(a: Point, b: Point, bend: number) {
  const length = Math.hypot(b.x - a.x, b.y - a.y) || 1
  // Left of a → b in screen coordinates, where y grows downwards.
  const normal = { x: (b.y - a.y) / length, y: -(b.x - a.x) / length }
  // A quadratic's midpoint lies halfway to its control point: twice the offset bends it by one.
  const control = {
    x: (a.x + b.x) / 2 + normal.x * bend * BEND_SPACING * 2,
    y: (a.y + b.y) / 2 + normal.y * bend * BEND_SPACING * 2,
  }
  const start = boundary(a, control)
  const end = boundary(b, control)
  return {
    path: `M ${start.x} ${start.y} Q ${control.x} ${control.y} ${end.x} ${end.y}`,
    // The curve's midpoint.
    label: { x: (start.x + 2 * control.x + end.x) / 4, y: (start.y + 2 * control.y + end.y) / 4 },
    labelAlign: 'center' as const,
  }
}

/**
 * An arc out of a class's right end and back, where links between classes (centre to
 * centre, through the wide node's top or bottom) rarely leave; larger loops nest outside
 * smaller ones.
 */
function loopPath(c: Point, size: number) {
  const right = c.x + NODE_SIZE.width / 2
  const reach = LOOP_REACH + LOOP_STEP * (size - 1)
  const spread = 8 + 6 * (size - 1)
  const [y0, y1] = [c.y - spread, c.y + spread]
  return {
    path: `M ${right} ${y0} C ${right + reach} ${y0 - spread * 2}, ${right + reach} ${y1 + spread * 2}, ${right} ${y1}`,
    // A cubic's midpoint: 3/4 of the way to its control points, here just outside the arc.
    label: { x: right + reach * 0.75 + 4, y: c.y },
    labelAlign: 'start' as const,
  }
}
