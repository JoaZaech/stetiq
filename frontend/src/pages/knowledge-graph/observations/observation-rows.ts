import type { DriftEvent, DriftThresholds, NotComparable, Observation } from '@/api/observations'
import { matchesSearch } from '@/lib/search'
import { DRIFT_FINDING, MISMATCH_FINDING, subjectKindLabel } from '../evaluation/findings'

export type ObservationStatus = 'Drift' | 'No Drift'
export const OBSERVATION_STATUSES: readonly ObservationStatus[] = ['Drift', 'No Drift']

/** One row of the Observations table: the Observation and the Drift event it raised, if any. */
export interface ObservationRow {
  observation: Observation
  drift: DriftEvent | undefined
  /** The Baseline Observation its Violation Rates were compared with; undefined for a run-end one. */
  baseline: Observation | undefined
  status: ObservationStatus
  /** How many Drift findings; 0 without Drift. */
  findings: number
}

/** The rows, newest first (the server sends Observations oldest first). */
export function observationRows(observations: readonly Observation[], driftEvents: readonly DriftEvent[]): ObservationRow[] {
  const byObservation = new Map(driftEvents.map((e) => [e.observation_id, e]))
  const byId = new Map(observations.map((o) => [o.id, o]))
  return [...observations].reverse().map((observation) => {
    const drift = byObservation.get(observation.id)
    const baseline = observation.baseline_observation_id ? byId.get(observation.baseline_observation_id) : undefined
    return { observation, drift, baseline, status: drift ? 'Drift' : 'No Drift', findings: drift?.findings.length ?? 0 }
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

const points = new Intl.NumberFormat('en', { maximumFractionDigits: 1 })

/**
 * `max drop off · max rise 50% · max violation rise 1 pt`; an event from before Violation
 * Rates lacks the last one, which was off.
 */
export function formatThresholds(thresholds: DriftThresholds): string {
  const part = (label: string, value: number | null) => `${label} ${value === null ? 'off' : percent.format(value)}`
  const violation = thresholds.max_violation_increase ?? null
  const inPoints = (value: number) => `${points.format(value * 100)} ${value === 0.01 ? 'pt' : 'pts'}`
  return [
    part('max drop', thresholds.max_count_drop),
    part('max rise', thresholds.max_count_increase),
    `max violation rise ${violation === null ? 'off' : inPoints(violation)}`,
  ].join(' · ')
}

/** One row of an Observation's not-comparable list. */
export interface NotComparableRow {
  subject: string
  /** "Class", "Relation", "Attribute", "Pattern" */
  kind: string
  /** The check, e.g. "Violation Rate: Required but not always set". */
  check: string
  reason: string
}

/** The checks an Observation could not compare, sorted by subject. */
export function notComparableRows(entries: readonly NotComparable[]): NotComparableRow[] {
  return entries
    .map((e) => ({
      subject: e.subject,
      kind: subjectKindLabel(e.subject_kind),
      check: e.violation ? `Violation Rate: ${MISMATCH_FINDING[e.violation]}` : DRIFT_FINDING[e.check],
      reason: e.reason,
    }))
    .sort((a, b) => a.subject.localeCompare(b.subject) || a.check.localeCompare(b.check))
}
