import type { EvaluationResult } from '@/api/ontology-versions'
import type { ConstructionRun } from '@/api/runs'
import type { MetricPoint } from '@/lib/metric-charts'
import { evaluatorMetrics } from '../versions/evaluator-metrics'

/** A compared value; `null` where a run has none (e.g. a param it did not log). */
export type ComparedValue = string | number | null

/** One key across the compared runs: `values[i]` belongs to `runs[i]`. */
export interface ComparisonRow<V extends ComparedValue = ComparedValue> {
  key: string
  values: V[]
}

/**
 * Runs side by side, as `Client.compare_runs` composes them: `values[i]` and
 * `conformance[i]` belong to `runs[i]`.
 */
export interface RunComparison {
  runs: readonly ConstructionRun[]
  declaredOntology: number[]
  candidate: (number | null)[]
  /** Conformance scores; `null` for a run without an Observation. */
  conformance: (number | null)[]
  params: ComparisonRow<string | null>[]
  metrics: ComparisonRow<number | null>[]
  /** The latest run-level Evaluator results, keyed `<evaluator>/<metric>` (`evaluatorMetrics`). */
  evaluations: ComparisonRow<number | null>[]
}

/** One row per key over `records` (one per run), sorted by key. */
function rows<V extends string | number>(records: readonly Readonly<Record<string, V>>[]): ComparisonRow<V | null>[] {
  const keys = [...new Set(records.flatMap((r) => Object.keys(r)))].sort((a, b) => a.localeCompare(b))
  return keys.map((key) => ({ key, values: records.map((r) => r[key] ?? null) }))
}

/** `evaluations[i]` are `runs[i]`'s Evaluator results (the run evaluations route). */
export function compareRuns(
  runs: readonly ConstructionRun[],
  evaluations: readonly (readonly EvaluationResult[])[],
): RunComparison {
  return {
    runs,
    declaredOntology: runs.map((r) => r.ontology_version),
    candidate: runs.map((r) => r.candidate_version),
    conformance: runs.map((r) => r.conformance?.score ?? null),
    params: rows(runs.map((r) => r.params)),
    metrics: rows(runs.map((r) => r.metrics)),
    evaluations: rows(evaluations.map(evaluatorMetrics)),
  }
}

/** Whether the runs' values are not all the same ("Show diff only" keeps these rows). */
export function differs(values: readonly ComparedValue[]): boolean {
  return values.some((v) => v !== values[0])
}

/** The Conformance score's name in the run charts, next to the run metrics. */
export const CONFORMANCE_METRIC = 'Conformance'

/**
 * Each run at its start time, with its metrics, Conformance score and Evaluator results
 * (keyed `<evaluator>/<metric>`, see `evaluatorMetrics`), for the run charts.
 * `evaluations` are the Knowledge Graph-wide run results; each joins its run by `subject_id`.
 */
export function runChartPoints(
  runs: readonly ConstructionRun[],
  evaluations: readonly EvaluationResult[] = [],
): MetricPoint[] {
  const byRun = new Map<string, EvaluationResult[]>()
  for (const result of evaluations) byRun.set(result.subject_id, [...(byRun.get(result.subject_id) ?? []), result])
  return runs.map((run) => ({
    x: Date.parse(run.started_at),
    metrics: {
      ...run.metrics,
      ...(run.conformance === null ? {} : { [CONFORMANCE_METRIC]: run.conformance.score }),
      ...evaluatorMetrics(byRun.get(run.id) ?? []),
    },
  }))
}
