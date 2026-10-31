import { useViewParam } from '@/lib/view-param'
import { MAP_VIEWS } from '../map-view'

/**
 * The Table / Map toggle shared by the Changes tab and the Compare page: Map by default
 * (`?view=` absent), as on the Ontology tab, and its changes as a grid at `?view=table`.
 */
export function useComparisonView() {
  return useViewParam(MAP_VIEWS)
}
