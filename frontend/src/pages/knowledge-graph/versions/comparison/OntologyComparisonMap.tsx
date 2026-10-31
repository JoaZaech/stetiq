import { ErrorAlert } from '@/components/ErrorAlert'
import { Skeleton } from '@/components/ui/skeleton'
import { cn } from '@/lib/utils'
import { MAP_HEIGHT } from '../map-view'
import { OntologyMap } from '../map/OntologyMap'
import { useOntologyComparison } from './use-ontology-comparison'

/**
 * Loads versions `base` and `target` and their Ontology Diff, and draws them superimposed
 * on one Map: the Changes tab's Map, and the Compare page's for any two versions. Its
 * filters go in `filtersIn` (`useMapFiltersSlot`).
 */
export function OntologyComparisonMap({
  knowledgeGraph,
  base,
  target,
  filtersIn,
}: {
  knowledgeGraph: string
  base: number
  target: number
  filtersIn: HTMLElement | null
}) {
  const { comparison, error } = useOntologyComparison(knowledgeGraph, base, target)
  if (error) return <ErrorAlert error={error} />
  if (!comparison) return <Skeleton className={cn(MAP_HEIGHT, 'w-full')} />
  return <OntologyMap comparison={comparison} filtersIn={filtersIn} />
}
