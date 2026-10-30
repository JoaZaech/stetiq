import { Network, Table2 } from 'lucide-react'
import type { ViewOption } from '@/components/ViewToggle'
import { useViewParam } from '@/lib/view-param'

/** How a comparison of two versions is shown: a superimposed Map, or the Ontology Diff as a list. */
export type ComparisonView = 'map' | 'table'

const VIEWS: readonly [ComparisonView, ...ComparisonView[]] = ['map', 'table']

export const COMPARISON_VIEW_OPTIONS: readonly ViewOption<ComparisonView>[] = [
  { value: 'table', label: 'Table', icon: Table2 },
  { value: 'map', label: 'Map', icon: Network },
]

/**
 * The Table / Map toggle shared by the Changes tab and the Compare page: Map by default
 * (`?view=` absent), as on the Ontology tab, and Table at `?view=table`.
 */
export function useComparisonView() {
  return useViewParam(VIEWS)
}
