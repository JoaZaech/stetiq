import { type Ref, useId, useMemo, useRef, useState, type ReactNode } from 'react'
import { ChevronDown, ChevronRight, Search } from 'lucide-react'
import { useSearchParams } from 'react-router'
import type { Ontology } from '@/api/ontology-versions'
import { ColumnPicker } from '@/components/ColumnPicker'
import { DataTable, DataTableRowCount } from '@/components/DataTable'
import { ViewToggle } from '@/components/ViewToggle'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { createDataTableColumnHelper, filterColumn, useDataTable } from '@/lib/data-table'
import { type DataTableParamsOptions, useDataTableParams } from '@/lib/data-table-params'
import { useViewParam } from '@/lib/view-param'
import { attributeRows } from './attribute-rows'
import { AttributesGrid } from './AttributesGrid'
import { type ClassRow, type ConceptTables, conceptTables, searchConcepts } from './concepts'
import { MAP_VIEW_OPTIONS, MAP_VIEWS } from './map-view'
import { OntologyMap } from './OntologyMap'
import { useOntologyVersionTab } from './version-context'

/**
 * The version page's Ontology tab: a Map of the Ontology by default (`?view=` absent), or
 * its Concepts as a Table (`?view=table`): classes, relations and attributes stacked in
 * collapsible sections under a jump bar. The Concept search (`?q=`) drives both: it
 * filters the Table and highlights on the Map.
 */
export function OntologyTab() {
  const version = useOntologyVersionTab()
  const [view, setView] = useViewParam(MAP_VIEWS)
  const [params, setParams] = useSearchParams()
  const query = params.get('q') ?? ''

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-4">
        <div className="relative w-full max-w-sm">
          <Search className="absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-muted-foreground" aria-hidden />
          <Input
            type="search"
            aria-label="Search Concepts"
            placeholder="Search Concepts"
            className="pl-8"
            value={query}
            onChange={(e) =>
              setParams(
                (p) => {
                  if (e.target.value) p.set('q', e.target.value)
                  else p.delete('q')
                  return p
                },
                { replace: true },
              )
            }
          />
        </div>
        <ViewToggle options={MAP_VIEW_OPTIONS} mode={view} onChange={setView} />
      </div>
      {view === 'map' ? (
        <OntologyMap ontology={version.ontology} query={query} />
      ) : (
        <OntologyTables ontology={version.ontology} query={query} />
      )}
    </div>
  )
}

type SectionId = 'classes' | 'relations' | 'attributes'

/** What each section means in the Ontology, in glossary words. */
const SECTIONS: readonly { id: SectionId; title: string; purpose: string }[] = [
  {
    id: 'classes',
    title: 'Classes',
    purpose:
      'Classes are the kinds of things the Knowledge Graph stores; an indented class is a subclass and inherits its superclass’s attributes and relations.',
  },
  {
    id: 'relations',
    title: 'Relations',
    purpose: 'Relations say how classes connect; each Pattern says which class may link to which through the relation.',
  },
  {
    id: 'attributes',
    title: 'Attributes',
    purpose: 'Attributes are the fields stored on a class or relation.',
  },
]

function OntologyTables({ ontology, query }: { ontology: Ontology; query: string }) {
  const all = useMemo(() => conceptTables(ontology), [ontology])
  const { relations } = searchConcepts(all, query)
  const attributes = useMemo(() => attributeRows(ontology), [ontology])
  const [collapsed, setCollapsed] = useState<ReadonlySet<SectionId>>(new Set())
  const sections = useRef(new Map<SectionId, HTMLElement>())

  const toggle = (id: SectionId, open: boolean) =>
    setCollapsed((c) => {
      const next = new Set(c)
      if (open) next.delete(id)
      else next.add(id)
      return next
    })
  const jump = (id: SectionId) => {
    toggle(id, true)
    sections.current.get(id)?.scrollIntoView({ block: 'start' })
  }
  const body: Record<SectionId, ReactNode> = {
    classes: <ClassesGrid classes={all.classes} />,
    relations: <RelationsTable relations={relations} query={query} />,
    attributes: <AttributesGrid attributes={attributes} />,
  }

  return (
    <div className="space-y-6">
      <nav
        aria-label="Ontology sections"
        className="sticky top-0 z-10 -mx-1 flex items-center gap-1 border-b bg-background px-1 py-1.5 text-sm"
      >
        {SECTIONS.map((s, i) => (
          <span key={s.id} className="inline-flex items-center gap-1">
            {i > 0 && (
              <span aria-hidden className="text-muted-foreground">
                ·
              </span>
            )}
            <Button variant="ghost" size="sm" className="h-7 px-2" onClick={() => jump(s.id)}>
              {s.title} <span className="text-muted-foreground tabular-nums">{all[s.id].length}</span>
            </Button>
          </span>
        ))}
      </nav>
      {SECTIONS.map((s) => (
        <Section
          key={s.id}
          ref={(el) => {
            if (el) sections.current.set(s.id, el)
            else sections.current.delete(s.id)
          }}
          title={s.title}
          purpose={s.purpose}
          open={!collapsed.has(s.id)}
          onOpenChange={(open) => toggle(s.id, open)}
        >
          {body[s.id]}
        </Section>
      ))}
    </div>
  )
}

function Section({
  ref,
  title,
  purpose,
  open,
  onOpenChange,
  children,
}: {
  ref: Ref<HTMLElement>
  title: string
  purpose: string
  open: boolean
  onOpenChange: (open: boolean) => void
  children: ReactNode
}) {
  const id = useId()
  const Chevron = open ? ChevronDown : ChevronRight
  return (
    <section ref={ref} aria-labelledby={id} className="scroll-mt-12 space-y-2">
      <h2 id={id} className="text-sm font-semibold">
        <Button
          variant="ghost"
          size="sm"
          className="-ml-2 h-7 px-2 text-sm font-semibold"
          aria-expanded={open}
          aria-controls={`${id}-body`}
          onClick={() => onOpenChange(!open)}
        >
          <Chevron aria-hidden className="size-4" />
          {title}
        </Button>
      </h2>
      <div id={`${id}-body`} hidden={!open} className="space-y-2">
        <p className="text-sm text-muted-foreground">{purpose}</p>
        {children}
      </div>
    </section>
  )
}

const classColumn = createDataTableColumnHelper<ClassRow>()

const none = <span className="text-muted-foreground">—</span>

const lines = (items: readonly string[]) =>
  items.length === 0 ? (
    none
  ) : (
    <div className="font-mono text-xs">
      {items.map((item) => (
        <div key={item}>{item}</div>
      ))}
    </div>
  )

const classColumns = classColumn.columns([
  classColumn.accessor('label', {
    header: 'Class',
    ...filterColumn('text'),
    // Indented under its superclass while the rows keep hierarchy order (no sort).
    cell: ({ row, table }) => (
      <div style={{ paddingLeft: table.store.state.sorting.length === 0 ? `${row.original.depth * 1.25}rem` : 0 }}>
        <ConceptName label={row.original.label} deprecated={row.original.deprecated} />
      </div>
    ),
  }),
  classColumn.accessor('parent', {
    header: 'Superclass',
    ...filterColumn('values'),
    enableGlobalFilter: false,
    sortUndefined: 'last',
    cell: ({ getValue }) => getValue() ?? none,
  }),
  classColumn.accessor('attributes', {
    header: 'Attributes',
    sortFn: 'basic',
    enableGlobalFilter: false,
    cell: ({ row }) => (
      <span className="tabular-nums">
        {row.original.attributes}
        {row.original.inheritedAttributes > 0 && (
          <span className="text-muted-foreground" title="inherited">
            {' '}
            ({row.original.inheritedAttributes})
          </span>
        )}
      </span>
    ),
  }),
  classColumn.accessor('outgoing', {
    header: 'Outgoing',
    ...filterColumn('text'),
    enableSorting: false,
    enableGlobalFilter: false,
    cell: ({ getValue }) => lines(getValue()),
  }),
  classColumn.accessor('incoming', {
    header: 'Incoming',
    ...filterColumn('text'),
    enableSorting: false,
    enableGlobalFilter: false,
    cell: ({ getValue }) => lines(getValue()),
  }),
  classColumn.accessor('constraints', {
    header: 'Constraints',
    ...filterColumn('text'),
    enableSorting: false,
    enableGlobalFilter: false,
    cell: ({ getValue }) => (getValue().length === 0 ? none : getValue().join(', ')),
  }),
  classColumn.accessor('description', {
    header: 'Description',
    ...filterColumn('text'),
    enableSorting: false,
    cell: ({ getValue }) => <span className="text-muted-foreground">{getValue()}</span>,
  }),
  classColumn.accessor('deprecated', {
    header: 'Deprecated',
    ...filterColumn('toggle'),
    enableGlobalFilter: false,
    cell: ({ getValue }) => (getValue() ? 'Deprecated' : ''),
  }),
])

/**
 * The Classes grid's URL state. The search is the Concept search (`?q=`), matching a
 * class's name or description as the Map's search does.
 */
const CLASSES_GRID: DataTableParamsOptions = {
  key: 'classes',
  filters: {
    label: 'text',
    parent: 'values',
    outgoing: 'text',
    incoming: 'text',
    constraints: 'text',
    description: 'text',
    deprecated: 'toggle',
  },
  optional: ['deprecated'],
  search: 'q',
}

function ClassesGrid({ classes }: { classes: ClassRow[] }) {
  const grid = useDataTableParams(CLASSES_GRID)
  const table = useDataTable({
    data: classes,
    columns: classColumns,
    getRowId: (row) => row.label,
    globalFilterFn: 'includesString',
    ...grid.tableOptions,
  })
  return (
    <>
      <div className="flex items-center justify-between gap-4">
        <DataTableRowCount table={table} noun="classes" />
        <ColumnPicker
          groups={[{ label: 'Columns', columns: [{ id: 'deprecated', label: 'Deprecated' }] }]}
          visible={grid.shown}
          onToggle={grid.setShown}
        />
      </div>
      <DataTable table={table} label="Classes" empty="No classes match." />
    </>
  )
}

function RelationsTable({ relations, query }: { relations: ConceptTables['relations']; query: string }) {
  if (relations.length === 0) return <Empty title="relations" query={query} />
  return (
    <Table aria-label="Relations">
      <TableHeader>
        <TableRow>
          <TableHead>Relation</TableHead>
          <TableHead>Patterns</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {relations.map((r) => (
          <TableRow key={r.label}>
            <TableCell>
              <ConceptName label={r.label} description={r.description} deprecated={r.deprecated} />
            </TableCell>
            <TableCell className="font-mono text-xs">
              {r.patterns.map((p) => (
                <div key={p}>{p}</div>
              ))}
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  )
}

function Empty({ title, query }: { title: string; query: string }) {
  return (
    <p className="text-sm text-muted-foreground">
      {query.trim() ? `No ${title} match “${query.trim()}”.` : `This Ontology has no ${title}.`}
    </p>
  )
}

function ConceptName({
  label,
  description,
  deprecated = false,
}: {
  label: string
  description?: string
  deprecated?: boolean
}) {
  return (
    <div>
      <span className="font-medium">{label}</span>
      {deprecated && (
        <Badge variant="outline" className="ml-2">
          deprecated
        </Badge>
      )}
      {description && <div className="text-xs text-muted-foreground">{description}</div>}
    </div>
  )
}
