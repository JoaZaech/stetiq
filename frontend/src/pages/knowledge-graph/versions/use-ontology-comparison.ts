import { useMemo } from 'react'
import { useOntologyDiff } from '@/api/ontology-diff'
import { useOntologyVersion } from '@/api/ontology-versions'
import { compareOntologies, type OntologyComparison } from './ontology-map-comparison'

/**
 * Loads versions `base` and `target` and their Ontology Diff, and compares them: null
 * while loading, and the first error, if any. Behind both views of a comparison.
 */
export function useOntologyComparison(
  knowledgeGraph: string,
  base: number,
  target: number,
): { comparison: OntologyComparison | null; error: Error | null } {
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
  return { comparison, error: baseVersion.error ?? targetVersion.error ?? diff.error }
}
