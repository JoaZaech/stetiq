import { createContext, use } from 'react'
import type { ConceptSelection } from './concept-selection'

/** A class or relation, as the Table names and links it. */
export type TableConcept = { kind: 'class' | 'relation'; label: string }

/** What the Ontology Table's links do (see `OntologyTables`). */
export interface TableLinks {
  /** Selects `concept` and scrolls to its row, opening its section. */
  select: (concept: TableConcept) => void
  /** Scrolls to `owner`'s group of attributes, grouping by owner and opening it. */
  openGroup: (owner: string) => void
  /** Switches to the Map with `concept` selected. */
  showOnMap: (concept: ConceptSelection) => void
}

export const TableLinksContext = createContext<TableLinks | null>(null)

export function useTableLinks(): TableLinks {
  const links = use(TableLinksContext)
  if (!links) throw new Error('useTableLinks must be used inside the Ontology Table')
  return links
}

/** The DOM id of a class's or relation's row in the Table. */
export const conceptRowId = ({ kind, label }: TableConcept) => `ontology-${kind}-${label}`

/** The DOM id of an owner's group header in the Attributes grid. */
export const attributeGroupId = (owner: string) => `ontology-attributes-${owner}`
