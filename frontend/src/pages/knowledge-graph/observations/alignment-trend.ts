import type { AlignmentPoint } from '@/api/observations'
import type { ChartMarker, MetricSeries } from '@/lib/metric-charts'

const RUN: ChartMarker = { hollow: false, label: 'run' }
const ON_DEMAND: ChartMarker = { hollow: true, label: 'on demand' }

/**
 * The alignment trend as one Conformance line over time (x in epoch milliseconds): run
 * points filled, on-demand Observation points hollow, each naming the Ontology Version
 * it was judged against. It has no threshold, so it draws no bound.
 */
export function alignmentSeries(points: readonly AlignmentPoint[]): MetricSeries {
  return {
    metric: 'Conformance',
    points: points
      .map((p) => ({
        x: Date.parse(p.at),
        value: p.score,
        id: p.observation_id,
        marker: p.run_id === null ? ON_DEMAND : RUN,
        detail: `v${p.ontology_version}`,
      }))
      .sort((a, b) => a.x - b.x),
  }
}

/** Each scored Observation's point, by Observation id (a run's by its run-end Observation). */
export function alignmentByObservation(points: readonly AlignmentPoint[]): Map<string, AlignmentPoint> {
  return new Map(points.map((p) => [p.observation_id, p]))
}
