import { useId, useMemo, type ReactNode } from 'react'
import { Network, Search, Table2 } from 'lucide-react'
import { useSearchParams } from 'react-router'
import type { Ontology } from '@/api/ontology-versions'
import { ViewToggle, type ViewOption } from '@/components/ViewToggle'
import { Badge } from '@/components/ui/badge'
import { Input } from '@/components/ui/input'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { useViewParam } from '@/lib/view-param'
import { conceptTables, searchConcepts } from './concepts'
import { OntologyMap } from './OntologyMap'
import { useOntologyVersionTab } from './version-context'

type OntologyView = 'map' | 'table'

const VIEWS: readonly [OntologyView, ...OntologyView[]] = ['map', 'table']

const VIEW_OPTIONS: readonly ViewOption<OntologyView>[] = [
  { value: 'table', label: 'Table', icon: Table2 },
  { value: 'map', label: 'Map', icon: Network },
]

/**
 * The version page's Ontology tab: a Map of the Ontology by default (`?view=` absent), or
 * its Concepts as tables (`?view=table`) grouped as classes, relations and attributes. The
 * Concept search (`?q=`) drives both: it filters the tables and highlights on the Map.
 */
export function OntologyTab() {
  const version = useOntologyVersionTab()
  const [view, setView] = useViewParam(VIEWS)
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
        <ViewToggle options={VIEW_OPTIONS} mode={view} onChange={setView} />
      </div>
      {view === 'map' ? (
        <OntologyMap ontology={version.ontology} query={query} />
      ) : (
        <OntologyTables ontology={version.ontology} query={query} />
      )}
    </div>
  )
}

function OntologyTables({ ontology, query }: { ontology: Ontology; query: string }) {
  const all = useMemo(() => conceptTables(ontology), [ontology])
  const { classes, relations, attributes } = searchConcepts(all, query)

  return (
    <div className="space-y-8">
      <Group title="Classes" count={classes.length} query={query}>
        <Table aria-label="Classes">
          <TableHeader>
            <TableRow>
              <TableHead>Class</TableHead>
              <TableHead>Superclass</TableHead>
              <TableHead>Constraints</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {classes.map((c) => (
              <TableRow key={c.label}>
                <TableCell style={{ paddingLeft: `${0.5 + c.depth * 1.25}rem` }}>
                  <ConceptName label={c.label} description={c.description} deprecated={c.deprecated} />
                </TableCell>
                <TableCell>{c.parent}</TableCell>
                <TableCell>{c.constraints.join(', ')}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </Group>

      <Group title="Relations" count={relations.length} query={query}>
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
      </Group>

      <Group title="Attributes" count={attributes.length} query={query}>
        <Table aria-label="Attributes">
          <TableHeader>
            <TableRow>
              <TableHead>Class or relation</TableHead>
              <TableHead>Attribute</TableHead>
              <TableHead>Type</TableHead>
              <TableHead>Required</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {attributes.map((a) => (
              <TableRow key={`${a.owner}.${a.name}`}>
                <TableCell>{a.owner}</TableCell>
                <TableCell>
                  <ConceptName label={a.name} description={a.description} />
                </TableCell>
                <TableCell className="font-mono text-xs">{a.type}</TableCell>
                <TableCell>{a.required && 'Required'}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </Group>
    </div>
  )
}

function Group({
  title,
  count,
  query,
  children,
}: {
  title: string
  count: number
  query: string
  children: ReactNode
}) {
  const id = useId()
  const empty = query.trim()
    ? `No ${title.toLowerCase()} match “${query.trim()}”.`
    : `This Ontology has no ${title.toLowerCase()}.`
  return (
    <section aria-labelledby={id} className="space-y-2">
      <h2 id={id} className="text-sm font-semibold">
        {title} <span className="font-normal text-muted-foreground">{count}</span>
      </h2>
      {count > 0 ? children : <p className="text-sm text-muted-foreground">{empty}</p>}
    </section>
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
