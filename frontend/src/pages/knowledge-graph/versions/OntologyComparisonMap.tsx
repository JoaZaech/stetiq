import { useMemo } from 'react'
import { useOntologyDiff } from '@/api/ontology-diff'
import { useOntologyVersion } from '@/api/ontology-versions'
import { ErrorAlert } from '@/components/ErrorAlert'
import { Skeleton } from '@/components/ui/skeleton'
import { compareOntologies } from './ontology-map'
import { OntologyMap } from './OntologyMap'

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
  const baseVersion = useOntologyVersion(knowledgeGraph, base)
  const targetVersion = useOntologyVersion(knowledgeGraph, target)
  const diff = useOntologyDiff(knowledgeGraph, base, target)
  const comparison = useMemo(
    () =>
      baseVersion.data && targetVersion.data && diff.data
        ? compareOntologies(baseVersion.data.ontology, targetVersion.data.ontology, diff.data)
        : null,
    [baseVersion.data, targetVersion.data, diff.data],
  )

  const error = baseVersion.error ?? targetVersion.error ?? diff.error
  if (error) return <ErrorAlert error={error} />
  if (!comparison) return <Skeleton className="h-[32rem] w-full" />
  return <OntologyMap comparison={comparison} />
}
