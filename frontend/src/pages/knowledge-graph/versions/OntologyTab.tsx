import { useId, useMemo, type ReactNode } from 'react'
import { Search } from 'lucide-react'
import { useSearchParams } from 'react-router'
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
import { conceptTables, searchConcepts } from './concepts'
import { useOntologyVersionTab } from './version-context'

/** The version page's Ontology tab: its Concepts grouped as classes, relations and attributes. */
export function OntologyTab() {
  const version = useOntologyVersionTab()
  const [params, setParams] = useSearchParams()
  const query = params.get('q') ?? ''
  const all = useMemo(() => conceptTables(version.ontology), [version.ontology])
  const { classes, relations, attributes } = searchConcepts(all, query)

  return (
    <div className="space-y-8">
      <div className="relative max-w-sm">
        <Search className="absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-muted-foreground" aria-hidden />
        <Input
          type="search"
          aria-label="Search Concepts"
          placeholder="Search Concepts"
          className="pl-8"
          value={query}
          onChange={(e) =>
            setParams(e.target.value ? { q: e.target.value } : {}, { replace: true })
          }
        />
      </div>

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
