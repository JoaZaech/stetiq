import { createContext, use } from 'react'
import type { ConceptSelection } from './concept-selection'
import type { ClassOrRelation } from './concepts'

/** What the Ontology Table's links do (see `OntologyTables`). */
export interface TableLinks {
  /** Selects `concept` and scrolls to its row, opening its section. */
  select: (concept: ClassOrRelation) => void
  /**
   * Scrolls to `owner`'s group of attributes, grouping by owner and opening it; absent
   * where there are no attribute groups, as in a comparison's grid.
   */
  openGroup?: (owner: string) => void
  /** Switches to the Map with `concept` selected. */
  showOnMap: (concept: ConceptSelection) => void
}

export const TableLinksContext = createContext<TableLinks | null>(null)

export function useTableLinks(): TableLinks {
  const links = use(TableLinksContext)
  if (!links) throw new Error('useTableLinks must be used inside the Ontology Table')
  return links
}

/** A row's props for its highlight, when the selection covers it. */
export const selectedRowProps = (selected: boolean) => ({
  'aria-current': selected || undefined,
  'data-state': selected ? 'selected' : undefined,
})

/** The DOM id of a class's or relation's row in the Table. */
export const conceptRowId = ({ kind, label }: ClassOrRelation) => `ontology-${kind}-${label}`

/** The DOM id of an owner's group header in the Attributes grid. */
export const attributeGroupId = (owner: string) => `ontology-attributes-${owner}`
