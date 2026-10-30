import { ErrorAlert } from '@/components/ErrorAlert'
import { Skeleton } from '@/components/ui/skeleton'
import { OntologyMap } from './OntologyMap'
import { useOntologyComparison } from './use-ontology-comparison'

/**
 * Loads versions `base` and `target` and their Ontology Diff, and draws them superimposed
 * on one Map: the Changes tab's Map, and the Compare page's for any two versions.
 */
export function OntologyComparisonMap({
  knowledgeGraph,
  base,
  target,
}: {
  knowledgeGraph: string
  base: number
  target: number
}) {
  const { comparison, error } = useOntologyComparison(knowledgeGraph, base, target)
  if (error) return <ErrorAlert error={error} />
  if (!comparison) return <Skeleton className="h-[32rem] w-full" />
  return <OntologyMap comparison={comparison} />
}
