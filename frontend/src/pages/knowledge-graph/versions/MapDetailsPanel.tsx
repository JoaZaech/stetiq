import type { ReactNode } from 'react'
import { Badge } from '@/components/ui/badge'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { MapSidePanel } from './MapSidePanel'
import type { DetailProperty, MapDetails } from './ontology-map-focus'

/**
 * The Map's details on demand for the selected class or link: description, superclass,
 * attributes and constraints. Attributes appear only here, never on the canvas.
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
  return (
    <MapSidePanel
      label="Details"
      kind={details.kind === 'class' ? 'Class' : 'Relation'}
      title={
        <>
          {details.kind === 'class' ? details.label : details.relation}
          {details.deprecated && (
            <Badge variant="outline" className="ml-2">
              deprecated
            </Badge>
          )}
        </>
      }
      subtitle={
        details.kind === 'link' && (
          <div className="mt-1 font-mono text-xs break-all text-muted-foreground">{details.id}</div>
        )
      }
      onClose={onClose}
    >
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
    </MapSidePanel>
  )
}

function Properties({ properties }: { properties: DetailProperty[] }) {
  return (
    <section className="space-y-1">
      <h4 className="text-xs font-semibold">Attributes</h4>
      {properties.length === 0 ? (
        <p className="text-xs text-muted-foreground">No attributes.</p>
      ) : (
        <PropertyTable properties={properties} />
      )}
    </section>
  )
}

function PropertyTable({ properties }: { properties: DetailProperty[] }) {
  return (
    <Table aria-label="Attributes">
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
