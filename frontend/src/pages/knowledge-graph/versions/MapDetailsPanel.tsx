import type { ReactNode } from 'react'
import { X } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import type { DetailProperty, MapDetails } from './ontology-map-focus'

/**
 * The Map's details on demand for the selected class or link: description, superclass,
 * properties and constraints. Properties appear only here, never on the canvas.
 * `children` are further sections below the details, such as a comparison's change detail.
 */
export function MapDetailsPanel({
  details,
  onClose,
  children,
}: {
  details: MapDetails
  onClose: () => void
  children?: ReactNode
}) {
  const title = details.kind === 'class' ? details.label : details.relation

  return (
    <aside aria-label="Details" className="w-80 shrink-0 space-y-4 overflow-y-auto border-l bg-background p-4 text-sm">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="text-xs text-muted-foreground">{details.kind === 'class' ? 'Class' : 'Relation'}</div>
          <h3 className="truncate font-semibold">
            {title}
            {details.deprecated && (
              <Badge variant="outline" className="ml-2">
                deprecated
              </Badge>
            )}
          </h3>
          {details.kind === 'link' && (
            <div className="mt-1 font-mono text-xs break-all text-muted-foreground">{details.id}</div>
          )}
        </div>
        <Button variant="ghost" size="icon-sm" aria-label="Close details" onClick={onClose}>
          <X aria-hidden />
        </Button>
      </div>

      {details.description && <p className="text-muted-foreground">{details.description}</p>}

      {details.kind === 'class' && (
        <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1">
          <dt className="text-muted-foreground">Superclass</dt>
          <dd>{details.parent ?? '—'}</dd>
        </dl>
      )}

      <Properties properties={details.properties} />

      {details.kind === 'class' && details.constraints.length > 0 && (
        <section className="space-y-1">
          <h4 className="text-xs font-semibold">Constraints</h4>
          <ul className="font-mono text-xs">
            {details.constraints.map((c) => (
              <li key={c}>{c}</li>
            ))}
          </ul>
        </section>
      )}

      {children}
    </aside>
  )
}

function Properties({ properties }: { properties: DetailProperty[] }) {
  if (properties.length === 0) return <p className="text-xs text-muted-foreground">No properties.</p>
  return (
    <Table aria-label="Properties">
      <TableHeader>
        <TableRow>
          <TableHead>Name</TableHead>
          <TableHead>Type</TableHead>
          <TableHead>Required</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {properties.map((p) => (
          <TableRow key={p.name}>
            <TableCell className="whitespace-normal">
              <span className="font-medium">{p.name}</span>
              {p.inheritedFrom && (
                <div className="text-xs text-muted-foreground">inherited from {p.inheritedFrom}</div>
              )}
              {p.description && <div className="text-xs text-muted-foreground">{p.description}</div>}
            </TableCell>
            <TableCell className="font-mono text-xs">{p.type}</TableCell>
            <TableCell>{p.required && 'Required'}</TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  )
}
