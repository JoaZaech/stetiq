import { useViewParam } from '@/lib/view-param'
import { MAP_VIEWS } from './map-view'

/**
 * The Table / Map toggle shared by the Changes tab and the Compare page: Map by default
 * (`?view=` absent), as on the Ontology tab, and the Ontology Diff as a list at `?view=table`.
 */
export function useComparisonView() {
  return useViewParam(MAP_VIEWS)
}
