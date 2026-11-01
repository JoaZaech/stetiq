/**
 * Shapes metric values for the metric chart grid (`components/MetricChartGrid`), one
 * line chart per metric. Generic over the x-axis: the version charts use the version
 * number, the run charts the run start time (epoch milliseconds).
 */

/** Whatever is plotted along the x-axis (`id` names it, e.g. a run id), with the metrics it has. */
export interface MetricPoint {
  x: number
  id?: string
  metrics: Readonly<Record<string, number>>
}

/**
 * One plotted value. `status`, when the value is judged (e.g. by a Gate), colours the
 * point pass or fail; `label` says the same in text (e.g. "fail (preview)").
 */
export interface ChartPoint {
  x: number
  value: number
  id?: string
  status?: { passed: boolean; label: string }
}

/** A dashed horizontal line at `value`, e.g. a Gate's bound: `label` "min 0.6", `name` the Gate. */
export interface ReferenceLine {
  name: string
  label: string
  value: number
}

/**
 * One chart's line: a metric's values, ordered along the x-axis, with any reference lines
 * and a `note` shown in text under the title (e.g. where the points' verdicts came from).
 */
export interface MetricSeries {
  metric: string
  points: ChartPoint[]
  references?: ReferenceLine[]
  note?: string
}

/**
 * One series per metric, ordered by metric name. Points ordered by `x`; a point without
 * the metric (e.g. a version that was never evaluated by that Evaluator) is left out of
 * that metric's series, so the line joins the points that have a value.
 */
export function metricSeries(points: readonly MetricPoint[]): MetricSeries[] {
  const ordered = [...points].sort((a, b) => a.x - b.x)
  return metricNames(points).map((metric) => ({
    metric,
    points: ordered.flatMap((p) => {
      const value = p.metrics[metric]
      if (value === undefined) return []
      return [p.id === undefined ? { x: p.x, value } : { x: p.x, value, id: p.id }]
    }),
  }))
}

/** The series whose metric name contains `search` (case-insensitive); all for a blank one. */
export function filterMetricSeries<S extends MetricSeries>(series: readonly S[], search: string): S[] {
  const needle = search.trim().toLowerCase()
  return needle === '' ? [...series] : series.filter((s) => s.metric.toLowerCase().includes(needle))
}

/** Every metric name that occurs in `points`, sorted. */
export function metricNames(points: readonly Pick<MetricPoint, 'metrics'>[]): string[] {
  const names = new Set(points.flatMap((p) => Object.keys(p.metrics)))
  return [...names].sort((a, b) => a.localeCompare(b))
}
