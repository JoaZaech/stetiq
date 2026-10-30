import { Network, Table2 } from 'lucide-react'
import type { ViewOption } from '@/components/ViewToggle'
import { useViewParam } from '@/lib/view-param'

/** How a comparison of two versions is shown: the Ontology Diff as a list, or a superimposed Map. */
export type ComparisonView = 'table' | 'map'

const VIEWS: readonly [ComparisonView, ...ComparisonView[]] = ['table', 'map']

export const COMPARISON_VIEW_OPTIONS: readonly ViewOption<ComparisonView>[] = [
  { value: 'table', label: 'Table', icon: Table2 },
  { value: 'map', label: 'Map', icon: Network },
]

/**
 * The Table / Map toggle shared by the Changes tab and the Compare page: Table by default
 * (`?view=` absent), Map at `?view=map`.
 */
export function useComparisonView() {
  return useViewParam(VIEWS)
}
