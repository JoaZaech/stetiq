import { useMemo } from 'react'
import { useQueries } from '@tanstack/react-query'
import { type OntologyVersion, versionEvaluationsQuery } from '@/api/ontology-versions'
import { metricNames } from '@/lib/metric-charts'
import { evaluatorMetrics } from './evaluator-metrics'

/** The Evaluator metrics of every Ontology Version of a Knowledge Graph. */
export interface VersionMetrics {
  /** Metrics by version number, keyed `<evaluator>/<metric>`. */
  byVersion: ReadonlyMap<number, Readonly<Record<string, number>>>
  /** Every metric any version has, sorted. */
  names: string[]
  isPending: boolean
  error: Error | null
}

/**
 * Loads each version's Evaluator results (one request per version; the API has no
 * Knowledge Graph-wide evaluation listing) and keys them per version. Waits for
 * `versions` to load.
 */
export function useVersionMetrics(kg: string, versions: readonly OntologyVersion[] | undefined): VersionMetrics {
  const results = useQueries({
    queries: (versions ?? []).map((v) => versionEvaluationsQuery(kg, v.number)),
    combine: (queries) => ({
      data: queries.map((q) => q.data),
      isPending: queries.some((q) => q.isPending),
      error: queries.find((q) => q.error)?.error ?? null,
    }),
  })
  const { data, isPending, error } = results
  return useMemo(() => {
    const byVersion = new Map(
      (versions ?? []).map((v, i) => [v.number, evaluatorMetrics(data[i] ?? [])] as const),
    )
    return {
      byVersion,
      names: metricNames([...byVersion.values()].map((metrics) => ({ metrics }))),
      isPending: versions === undefined || isPending,
      error,
    }
  }, [versions, data, isPending, error])
}
