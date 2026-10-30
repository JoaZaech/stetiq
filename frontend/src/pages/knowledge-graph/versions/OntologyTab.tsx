import { type Ref, useEffect, useId, useMemo, useRef, useState, type ReactNode } from 'react'
import { ChevronDown, ChevronRight, Search } from 'lucide-react'
import { useSearchParams } from 'react-router'
import type { Ontology } from '@/api/ontology-versions'
import { ColumnPicker } from '@/components/ColumnPicker'
import { DataTable, DataTableRowCount } from '@/components/DataTable'
import { ViewToggle } from '@/components/ViewToggle'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { createDataTableColumnHelper, filterColumn, useDataTable } from '@/lib/data-table'
import { type DataTableParamsOptions, useDataTableParams } from '@/lib/data-table-params'
import { formatCount } from '@/lib/format'
import { useViewParam } from '@/lib/view-param'
import { attributeRows } from './attribute-rows'
import { AttributesGrid, type GroupRequest } from './AttributesGrid'
import {
  type ConceptSelection,
  isSelectedRow,
  type SelectedRows,
  selectedRows,
  useConceptSelection,
  useShowOnMap,
} from './concept-selection'
import { type ClassOrRelation, type ClassRow, type RelationRow, conceptTables } from './concepts'
import { MAP_VIEW_OPTIONS, MAP_VIEWS } from './map-view'
import { OntologyMap } from './OntologyMap'
import { conceptRowId, selectedRowProps, type TableLinks, TableLinksContext } from './table-links'
import { AttributeCountLink, ConceptLink, ShowOnMap } from './TableLinks'
import { useOntologyVersionTab } from './version-context'

/**
 * The version page's Ontology tab: a Map of the Ontology by default (`?view=` absent), or
 * its Concepts as a Table (`?view=table`): classes, relations and attributes stacked in
 * collapsible sections under a jump bar. The Concept search (`?q=`) drives both: it
 * filters the Table and highlights on the Map. So does the selection (`?select=`): it is
 * selected on the Map and highlighted in the Table.
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
        <OntologyTables ontology={version.ontology} />
      )}
    </div>
  )
}

type SectionId = 'classes' | 'relations' | 'attributes'

/**
 * What each section means in the Ontology, in glossary words, and what one of its rows
 * is, as its grid counts them.
 */
const SECTIONS: readonly { id: SectionId; title: string; row: [string, string]; purpose: string }[] = [
  {
    id: 'classes',
    title: 'Classes',
    row: ['class', 'classes'],
    purpose:
      'Classes are the kinds of things the Knowledge Graph stores; an indented class is a subclass and inherits its superclass’s attributes and relations.',
  },
  {
    id: 'relations',
    title: 'Relations',
    row: ['relation', 'relations'],
    purpose: 'Relations say how classes connect; each Pattern says which class may link to which through the relation.',
  },
  {
    id: 'attributes',
    title: 'Attributes',
    row: ['attribute', 'attributes'],
    purpose: 'Attributes are the fields stored on a class or relation.',
  },
]

/** The row a selection highlights first: a link's relation, a path's first class. */
function rowOf(ontology: Ontology, selection: ConceptSelection | null): ClassOrRelation | null {
  const { classes, relations } = selectedRows(ontology, selection)
  const [label] = [...classes, ...relations]
  if (label === undefined) return null
  return { kind: classes.has(label) ? 'class' : 'relation', label }
}

/** A request to scroll to a row by DOM id; `seq` tells a repeated request from the last. */
type ScrollRequest = { id: string; seq: number }

/**
 * The Table's three sections. Every class and relation name links to its row (selecting
 * it), attribute counts link to their owner's group, and each row can be shown on the
 * Map. It opens scrolled to the selection's row.
 */
function OntologyTables({ ontology }: { ontology: Ontology }) {
  const all = useMemo(() => conceptTables(ontology), [ontology])
  const attributes = useMemo(() => attributeRows(ontology), [ontology])
  const [collapsed, setCollapsed] = useState<ReadonlySet<SectionId>>(new Set())
  const sections = useRef(new Map<SectionId, HTMLElement>())
  const [selection, setSelection] = useConceptSelection()
  const highlighted = useMemo(() => selectedRows(ontology, selection), [ontology, selection])
  const showOnMap = useShowOnMap()
  const [scroll, setScroll] = useState<ScrollRequest | null>(() => {
    const row = rowOf(ontology, selection)
    return row && { id: conceptRowId(row), seq: 0 }
  })
  const [group, setGroup] = useState<GroupRequest | null>(null)

  useEffect(() => {
    if (scroll) document.getElementById(scroll.id)?.scrollIntoView({ block: 'center' })
  }, [scroll])

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
  const links = useMemo(
    (): TableLinks => {
      const open = (id: SectionId) => setCollapsed((c) => new Set([...c].filter((s) => s !== id)))
      return {
        select: (concept) => {
          setSelection(concept)
          open(concept.kind === 'class' ? 'classes' : 'relations')
          setScroll((s) => ({ id: conceptRowId(concept), seq: (s?.seq ?? 0) + 1 }))
        },
        openGroup: (owner) => {
          open('attributes')
          setGroup((g) => ({ owner, seq: (g?.seq ?? 0) + 1 }))
        },
        showOnMap,
      }
    },
    [setSelection, showOnMap],
  )
  // Each section's rows: the attributes inherited by each subclass included.
  const rows: Record<SectionId, number> = {
    classes: all.classes.length,
    relations: all.relations.length,
    attributes: attributes.length,
  }
  const body: Record<SectionId, ReactNode> = {
    classes: <ClassesGrid classes={all.classes} selected={highlighted} />,
    relations: <RelationsGrid relations={all.relations} selected={highlighted} />,
    attributes: <AttributesGrid attributes={attributes} reveal={group} />,
  }

  return (
    <TableLinksContext value={links}>
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
              <Button
                variant="ghost"
                size="sm"
                className="h-7 px-2"
                title={formatCount(rows[s.id], ...s.row)}
                onClick={() => jump(s.id)}
              >
                {s.title} <span className="text-muted-foreground tabular-nums">{rows[s.id]}</span>
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
    </TableLinksContext>
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

/** A row's props: its id to scroll to, and its highlight when selected. */
const rowProps = (concept: ClassOrRelation, selected: SelectedRows) => ({
  id: conceptRowId(concept),
  ...selectedRowProps(isSelectedRow(selected, concept)),
})

/** The column every row ends in: its "Show on Map". */
const showOnMapColumn = (kind: ClassOrRelation['kind']) => ({
  id: 'map',
  header: '',
  cell: ({ row }: { row: { original: { label: string } } }) => <ShowOnMap concept={{ kind, label: row.original.label }} />,
})

const classColumn = createDataTableColumnHelper<ClassRow>()

const none = <span className="text-muted-foreground">—</span>

/** A class's outgoing or incoming relation as `ClassRow` has it: `HAS_TRIP → Trip`, `HAS_TRIP ← Route`. */
const CONNECTION = /^(.*) ([→←]) (.*)$/

/** A class's outgoing or incoming relations, one per line, each name a link. */
const connections = (items: readonly string[]) =>
  items.length === 0 ? (
    none
  ) : (
    <div className="font-mono text-xs">
      {items.map((item) => {
        const [, relation, arrow, other] = CONNECTION.exec(item) ?? []
        return (
          <div key={item}>
            {relation === undefined ? (
              item
            ) : (
              <>
                <ConceptLink concept={{ kind: 'relation', label: relation }} /> {arrow}{' '}
                <ConceptLink concept={{ kind: 'class', label: other }} />
              </>
            )}
          </div>
        )
      })}
    </div>
  )

const classColumns = classColumn.columns([
  classColumn.accessor('label', {
    header: 'Class',
    ...filterColumn('text'),
    // Indented under its superclass while the rows keep hierarchy order (no sort).
    cell: ({ row, table }) => (
      <div style={{ paddingLeft: table.store.state.sorting.length === 0 ? `${row.original.depth * 1.25}rem` : 0 }}>
        <ConceptName
          label={<ConceptLink concept={{ kind: 'class', label: row.original.label }} />}
          deprecated={row.original.deprecated}
        />
      </div>
    ),
  }),
  classColumn.accessor('parent', {
    header: 'Superclass',
    ...filterColumn('values'),
    enableGlobalFilter: false,
    sortUndefined: 'last',
    cell: ({ getValue }) => {
      const parent = getValue()
      return parent === undefined ? none : <ConceptLink concept={{ kind: 'class', label: parent }} />
    },
  }),
  classColumn.accessor('attributes', {
    header: 'Attributes',
    sortFn: 'basic',
    enableGlobalFilter: false,
    cell: ({ row }) => {
      const { label, attributes, inheritedAttributes } = row.original
      const count = (
        <span className="tabular-nums">
          {attributes}
          {inheritedAttributes > 0 && (
            <span className="text-muted-foreground" title="inherited">
              {' '}
              ({inheritedAttributes})
            </span>
          )}
        </span>
      )
      const total = attributes + inheritedAttributes
      return total === 0 ? (
        count
      ) : (
        <AttributeCountLink owner={label} count={total}>
          {count}
        </AttributeCountLink>
      )
    },
  }),
  classColumn.accessor('outgoing', {
    header: 'Outgoing',
    ...filterColumn('text'),
    enableSorting: false,
    enableGlobalFilter: false,
    cell: ({ getValue }) => connections(getValue()),
  }),
  classColumn.accessor('incoming', {
    header: 'Incoming',
    ...filterColumn('text'),
    enableSorting: false,
    enableGlobalFilter: false,
    cell: ({ getValue }) => connections(getValue()),
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
  classColumn.display(showOnMapColumn('class')),
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

function ClassesGrid({ classes, selected }: { classes: ClassRow[]; selected: SelectedRows }) {
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
      <DataTable
        table={table}
        label="Classes"
        empty="No classes match."
        rowProps={(row) => rowProps({ kind: 'class', label: row.original.label }, selected)}
      />
    </>
  )
}

const relationColumn = createDataTableColumnHelper<RelationRow>()

/** A Pattern `(Source)-[REL]->(Target)`, its two class names set apart from the syntax. */
const PATTERN = /^\((.*)\)-\[(.*)\]->\((.*)\)$/

function PatternText({ pattern }: { pattern: string }) {
  const [, source, relation, target] = PATTERN.exec(pattern) ?? []
  if (source === undefined) return <div>{pattern}</div>
  const syntax = (text: string) => <span className="text-muted-foreground">{text}</span>
  return (
    <div>
      {syntax('(')}
      <span className="font-semibold">
        <ConceptLink concept={{ kind: 'class', label: source }} />
      </span>
      {syntax(')-[')}
      <ConceptLink concept={{ kind: 'relation', label: relation }} />
      {syntax(']->(')}
      <span className="font-semibold">
        <ConceptLink concept={{ kind: 'class', label: target }} />
      </span>
      {syntax(')')}
    </div>
  )
}

const relationColumns = relationColumn.columns([
  relationColumn.accessor('label', {
    header: 'Relation',
    ...filterColumn('text'),
    cell: ({ row }) => (
      <ConceptName
        label={<ConceptLink concept={{ kind: 'relation', label: row.original.label }} />}
        deprecated={row.original.deprecated}
      />
    ),
  }),
  relationColumn.accessor('patterns', {
    header: 'Patterns',
    ...filterColumn('text'),
    enableSorting: false,
    enableGlobalFilter: false,
    cell: ({ getValue }) =>
      getValue().length === 0 ? (
        none
      ) : (
        <div className="font-mono text-xs">
          {getValue().map((p) => (
            <PatternText key={p} pattern={p} />
          ))}
        </div>
      ),
  }),
  relationColumn.accessor('attributes', {
    header: 'Attributes',
    sortFn: 'basic',
    enableGlobalFilter: false,
    cell: ({ row }) => {
      const { label, attributes } = row.original
      const count = <span className="tabular-nums">{attributes}</span>
      return attributes === 0 ? (
        count
      ) : (
        <AttributeCountLink owner={label} count={attributes}>
          {count}
        </AttributeCountLink>
      )
    },
  }),
  relationColumn.accessor('description', {
    header: 'Description',
    ...filterColumn('text'),
    enableSorting: false,
    cell: ({ getValue }) => <span className="text-muted-foreground">{getValue()}</span>,
  }),
  relationColumn.accessor('deprecated', {
    header: 'Deprecated',
    ...filterColumn('toggle'),
    enableGlobalFilter: false,
    cell: ({ getValue }) => (getValue() ? 'Deprecated' : ''),
  }),
  relationColumn.display(showOnMapColumn('relation')),
])

/**
 * The Relations grid's URL state. The search is the Concept search (`?q=`), matching a
 * relation's name or description as the Map's search does.
 */
const RELATIONS_GRID: DataTableParamsOptions = {
  key: 'relations',
  filters: { label: 'text', patterns: 'text', description: 'text', deprecated: 'toggle' },
  optional: ['deprecated'],
  search: 'q',
}

function RelationsGrid({ relations, selected }: { relations: RelationRow[]; selected: SelectedRows }) {
  const grid = useDataTableParams(RELATIONS_GRID)
  const table = useDataTable({
    data: relations,
    columns: relationColumns,
    getRowId: (row) => row.label,
    globalFilterFn: 'includesString',
    ...grid.tableOptions,
  })
  return (
    <>
      <div className="flex items-center justify-between gap-4">
        <DataTableRowCount table={table} noun="relations" />
        <ColumnPicker
          groups={[{ label: 'Columns', columns: [{ id: 'deprecated', label: 'Deprecated' }] }]}
          visible={grid.shown}
          onToggle={grid.setShown}
        />
      </div>
      <DataTable
        table={table}
        label="Relations"
        empty="No relations match."
        rowProps={(row) => rowProps({ kind: 'relation', label: row.original.label }, selected)}
      />
    </>
  )
}

export function ConceptName({
  label,
  description,
  deprecated = false,
}: {
  label: ReactNode
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
