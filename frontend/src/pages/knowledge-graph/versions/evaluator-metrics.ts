import type { EvaluationResult } from '@/api/ontology-versions'

/** One Evaluator metric of a subject, as `evaluator · metric · value · Use Case Version`. */
export interface EvaluatorMetricRow {
  /** `<evaluator>/<metric>`: names the metric across subjects (columns, charts). */
  key: string
  /** The Evaluator, with its parameters when it has any, e.g. `coverage (min=1)`. */
  evaluator: string
  metric: string
  value: number
  useCaseVersion: number | null
}

/**
 * An Evaluator's name with its parameters (in key order) when it has any, e.g.
 * `coverage (gold="v2", min=1)`: one name per configuration.
 */
export function evaluatorLabel(evaluator: string, parameters: Readonly<Record<string, unknown>>): string {
  const params = Object.entries(parameters).sort(([a], [b]) => a.localeCompare(b))
  return params.length === 0
    ? evaluator
    : `${evaluator} (${params.map(([k, v]) => `${k}=${JSON.stringify(v)}`).join(', ')})`
}

/**
 * The `<evaluator>/<metric>` key that names one metric of one Evaluator configuration
 * across subjects (columns, charts, a metric Gate's KPI), e.g. `coverage (min=1)/ratio`.
 */
export function evaluatorMetricKey(
  evaluator: string,
  parameters: Readonly<Record<string, unknown>>,
  metric: string,
): string {
  return `${evaluatorLabel(evaluator, parameters)}/${metric}`
}

/** One row per metric, ordered by Evaluator then metric. */
export function metricRows(results: readonly EvaluationResult[]): EvaluatorMetricRow[] {
  return [...results]
    .sort((a, b) => a.evaluator.localeCompare(b.evaluator))
    .flatMap((result) => {
      const evaluator = evaluatorLabel(result.evaluator, result.parameters)
      return Object.entries(result.metrics)
        .sort(([a], [b]) => a.localeCompare(b))
        .map(([metric, value]) => ({
          key: evaluatorMetricKey(result.evaluator, result.parameters, metric),
          evaluator,
          metric,
          value,
          useCaseVersion: result.use_case_version,
        }))
    })
}

/** A subject's Evaluator metrics by `<evaluator>/<metric>` key (see `metricRows`). */
export function evaluatorMetrics(results: readonly EvaluationResult[]): Record<string, number> {
  return Object.fromEntries(metricRows(results).map((row) => [row.key, row.value]))
}
