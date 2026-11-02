import type { DriftEvent, DriftThresholds, Observation } from '@/api/observations'
import { matchesSearch } from '@/lib/search'

export type ObservationStatus = 'Drift' | 'No Drift'
export const OBSERVATION_STATUSES: readonly ObservationStatus[] = ['Drift', 'No Drift']

/** One row of the Observations table: the Observation and the Drift event it raised, if any. */
export interface ObservationRow {
  observation: Observation
  drift: DriftEvent | undefined
  status: ObservationStatus
  /** How many Drift findings; 0 without Drift. */
  findings: number
}

/** The rows, newest first (the server sends Observations oldest first). */
export function observationRows(observations: readonly Observation[], driftEvents: readonly DriftEvent[]): ObservationRow[] {
  const byObservation = new Map(driftEvents.map((e) => [e.observation_id, e]))
  return [...observations].reverse().map((observation) => {
    const drift = byObservation.get(observation.id)
    return { observation, drift, status: drift ? 'Drift' : 'No Drift', findings: drift?.findings.length ?? 0 }
  })
}

/** The rows the search (run id, version, Contract Alias) and the Status filter (`''` for all) leave. */
export function filterObservationRows(rows: readonly ObservationRow[], query: string, status: string): ObservationRow[] {
  return rows.filter(
    (r) =>
      (status === '' || r.status === status) &&
      matchesSearch(query, [
        r.observation.run_id,
        r.drift && `v${r.drift.ontology_version}`,
        r.drift?.contract_alias,
      ]),
  )
}

const percent = new Intl.NumberFormat('en', { style: 'percent', maximumFractionDigits: 1 })

/** `max drop off · max rise 50%` */
export function formatThresholds(thresholds: DriftThresholds): string {
  const part = (label: string, value: number | null) => `${label} ${value === null ? 'off' : percent.format(value)}`
  return [part('max drop', thresholds.max_count_drop), part('max rise', thresholds.max_count_increase)].join(' · ')
}
