import { useMemo } from 'react'
import { type EvaluationResult, useAllVersionEvaluations } from '@/api/ontology-versions'
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

/** Each version's latest Evaluator results, grouped by version number. */
function resultsByVersion(results: readonly EvaluationResult[]): Map<number, EvaluationResult[]> {
  const byVersion = new Map<number, EvaluationResult[]>()
  for (const result of results) {
    const number = Number(result.subject_id)
    byVersion.set(number, [...(byVersion.get(number) ?? []), result])
  }
  return byVersion
}

/**
 * Loads the latest Evaluator results of every version in one request (the Knowledge
 * Graph-wide evaluations route) and keys their metrics per version.
 */
export function useVersionMetrics(kg: string): VersionMetrics {
  const { data, isPending, error } = useAllVersionEvaluations(kg)
  return useMemo(() => {
    const byVersion = new Map(
      [...resultsByVersion(data ?? [])].map(([number, results]) => [number, evaluatorMetrics(results)] as const),
    )
    return {
      byVersion,
      names: metricNames([...byVersion.values()].map((metrics) => ({ metrics }))),
      isPending,
      error,
    }
  }, [data, isPending, error])
}
