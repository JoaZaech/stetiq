/**
 * Shapes metric values for the metric chart grid (`components/MetricChartGrid`), one
 * line chart per metric. Generic over the x-axis: the version charts use the version
 * number, the run charts the run start time (epoch milliseconds).
 */

/** Whatever is plotted along the x-axis, with the metrics it has. */
export interface MetricPoint {
  x: number
  metrics: Readonly<Record<string, number>>
}

/** One chart's line: a metric's values, ordered along the x-axis. */
export interface MetricSeries {
  metric: string
  points: { x: number; value: number }[]
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
      return value === undefined ? [] : [{ x: p.x, value }]
    }),
  }))
}

/** The series whose metric name contains `search` (case-insensitive); all for a blank one. */
export function filterMetricSeries(series: readonly MetricSeries[], search: string): MetricSeries[] {
  const needle = search.trim().toLowerCase()
  return needle === '' ? [...series] : series.filter((s) => s.metric.toLowerCase().includes(needle))
}

/** Every metric name that occurs in `points`, sorted. */
export function metricNames(points: readonly Pick<MetricPoint, 'metrics'>[]): string[] {
  const names = new Set(points.flatMap((p) => Object.keys(p.metrics)))
  return [...names].sort((a, b) => a.localeCompare(b))
}
