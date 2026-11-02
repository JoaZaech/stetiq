import type { DriftFinding } from '@/api/observations'
import type { Mismatch, MismatchSubjectKind } from '@/api/runs'
import type { StatusTone } from '@/components/status-tones'
import { conceptKindLabel } from '@/lib/concept-kind'
import { matchesSearch } from '@/lib/search'

/**
 * One row of the findings table every evaluation shares: a Conformance mismatch of a run
 * or a Drift finding of an Observation, in the same four columns.
 */
export interface FindingRow {
  /** e.g. `Sensor`, `Sensor.unit`, `(Machine)-[HAS_SENSOR]->(Sensor)` */
  subject: string
  /** "Class", "Relation", "Attribute", "Pattern" */
  kind: string
  /** What was found, e.g. "Observed but not declared", "Count dropped". */
  finding: string
  /** The change or the detail, e.g. `12 → 6 (−50%)`; empty when the finding says it all. */
  change: string
  tone: StatusTone
  /** A Drift finding only: whether the previous Observation had it too. */
  status?: 'New' | 'Persisting'
}

export const MISMATCH_FINDING: Record<Mismatch['kind'], string> = {
  absent: 'Declared but not observed',
  undeclared: 'Observed but not declared',
  type_mismatch: 'Undeclared value type',
  required_missing: 'Required but not always set',
  cardinality_violation: 'Outside the cardinality',
  value_outside_vocabulary: 'Value outside the Vocabulary',
  deprecated_value: 'Deprecated value',
}

export const DRIFT_FINDING: Record<DriftFinding['kind'], string> = {
  undeclared: 'Observed but not declared',
  vanished: 'No longer observed',
  undeclared_value: 'Value outside the Vocabulary',
  count_drop: 'Count dropped',
  count_increase: 'Count rose',
  violation_increase: 'Violation Rate rose',
}

export const subjectKindLabel = (kind: MismatchSubjectKind) => (kind === 'pattern' ? 'Pattern' : conceptKindLabel(kind))

/** A run's Conformance mismatches as rows; a deprecated value conforms, so it is neutral. */
export function findingsFromMismatches(mismatches: readonly Mismatch[]): FindingRow[] {
  return sortRows(
    mismatches.map((m) => ({
      subject: m.subject,
      kind: subjectKindLabel(m.subject_kind),
      finding: MISMATCH_FINDING[m.kind],
      change: m.value !== undefined ? valueChange(m.value, m.count) : m.detail,
      tone: m.kind === 'deprecated_value' ? 'neutral' : 'failure',
    })),
  )
}

/**
 * An Observation's Drift findings as rows, new before persisting: a count change as
 * `12 → 6 (−50%)`, a risen Violation Rate as `Required but not always set: 0.5% → 3% (+2.5 pts)`.
 */
export function findingsFromDrift(findings: readonly DriftFinding[]): FindingRow[] {
  const rows = sortRows(
    findings.map((f) => ({
      subject: f.subject,
      kind: subjectKindLabel(f.subject_kind),
      finding: DRIFT_FINDING[f.kind],
      change: driftChange(f),
      tone: 'warning',
      status: f.new ? 'New' : 'Persisting',
    })),
  )
  return [...rows.filter((r) => r.status === 'New'), ...rows.filter((r) => r.status !== 'New')]
}

function driftChange(f: DriftFinding): string {
  if (f.previous_count !== null && f.observed_count !== null) return countChange(f.previous_count, f.observed_count)
  if (f.violation !== undefined && f.baseline_rate !== undefined && f.observed_rate !== undefined) {
    return `${MISMATCH_FINDING[f.violation]}: ${rateChange(f.baseline_rate, f.observed_rate)}`
  }
  if (f.value !== undefined) {
    const change = valueChange(f.value, f.count)
    return f.share === undefined ? change : `${change} (${percent.format(f.share)})`
  }
  return f.detail
}

const percent = new Intl.NumberFormat('en', { style: 'percent', maximumFractionDigits: 1 })
const points = new Intl.NumberFormat('en', { maximumFractionDigits: 1, signDisplay: 'exceptZero' })

/** `0.5% → 3% (+2.5 pts)`: a Violation Rate's change, in percentage points. */
export function rateChange(baseline: number, observed: number): string {
  const delta = points.format((observed - baseline) * 100).replace('-', '−')
  return `${percent.format(baseline)} → ${percent.format(observed)} (${delta} pts)`
}

const signedPercent = new Intl.NumberFormat('en', { style: 'percent', maximumFractionDigits: 0, signDisplay: 'exceptZero' })

/** `12 → 6 (−50%)`; from 0 there is no percentage. */
export function countChange(previous: number, observed: number): string {
  const arrow = `${previous} → ${observed}`
  if (previous === 0) return arrow
  return `${arrow} (${signedPercent.format((observed - previous) / previous).replace('-', '−')})`
}

const valueChange = (value: string, count?: number) => (count === undefined ? `“${value}”` : `“${value}” × ${count}`)

const sortRows = (rows: FindingRow[]) =>
  rows.sort((a, b) => a.finding.localeCompare(b.finding) || a.subject.localeCompare(b.subject))

/** The findings table's filters: a kind and a finding, `''` for all, and the search. */
export interface FindingFilters {
  kind: string
  finding: string
  query: string
}

export function filterFindings(rows: readonly FindingRow[], { kind, finding, query }: FindingFilters): FindingRow[] {
  return rows.filter(
    (r) =>
      (kind === '' || r.kind === kind) &&
      (finding === '' || r.finding === finding) &&
      matchesSearch(query, [r.subject, r.change]),
  )
}

/** Each value of `key` among `rows` with how many rows hold it, most first. */
export function facetCounts(rows: readonly FindingRow[], key: 'kind' | 'finding'): [string, number][] {
  const counts = new Map<string, number>()
  for (const row of rows) counts.set(row[key], (counts.get(row[key]) ?? 0) + 1)
  return [...counts].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
}
