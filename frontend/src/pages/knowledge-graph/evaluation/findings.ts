import type { DriftFinding } from '@/api/observations'
import type { Mismatch, MismatchSubjectKind } from '@/api/runs'
import type { StatusTone } from '@/components/status-tones'
import { conceptKindLabel } from '@/lib/concept-kind'
import { formatPercent, formatPoints } from '@/lib/format'
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
  /** A Drift finding only: false when the previous Observation had it too (see `DRIFT_FINDING_STATUS`). */
  new?: boolean
}

/** A Drift finding's status, new or persisting, as its name and tone. */
export const DRIFT_FINDING_STATUS: Record<'new' | 'persisting', { label: string; tone: StatusTone }> = {
  new: { label: 'New', tone: 'warning' },
  persisting: { label: 'Persisting', tone: 'neutral' },
}

export const driftFindingStatus = (isNew: boolean) => DRIFT_FINDING_STATUS[isNew ? 'new' : 'persisting']

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
  coverage_drop: 'Coverage dropped',
  fill_rate_drop: 'Fill rate fell',
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
 * `12 → 6 (−50%)`, a risen Violation Rate as `Required but not always set: 0.5% → 3% (+2.5 pts)`,
 * a dropped Coverage as `Out-degree: 95% → 85% (−10 pts)`, a fallen fill rate as `100% → 80% (−20 pts)`.
 */
export function findingsFromDrift(findings: readonly DriftFinding[]): FindingRow[] {
  const rows = sortRows(
    findings.map((f) => ({
      subject: f.subject,
      kind: subjectKindLabel(f.subject_kind),
      finding: DRIFT_FINDING[f.kind],
      change: driftChange(f),
      tone: 'warning',
      new: f.new,
    })),
  )
  return [...rows.filter((r) => r.new), ...rows.filter((r) => !r.new)]
}

/** The Change column of a Drift finding, by kind; its detail when a field it needs is missing. */
function driftChange(f: DriftFinding): string {
  const rates = (show: (change: string) => string) =>
    f.baseline_rate !== undefined && f.observed_rate !== undefined ? show(rateChange(f.baseline_rate, f.observed_rate)) : f.detail
  switch (f.kind) {
    case 'count_drop':
    case 'count_increase':
      return f.previous_count !== null && f.observed_count !== null
        ? countChange(f.previous_count, f.observed_count)
        : f.detail
    case 'violation_increase': {
      if (f.violation === undefined) return f.detail
      const check = MISMATCH_FINDING[f.violation]
      const degree = f.direction === undefined ? '' : ` (${f.direction}-degree)`
      return rates((change) => `${check}${degree}: ${change}`)
    }
    case 'coverage_drop': {
      if (f.direction === undefined) return f.detail
      const degree = f.direction === 'out' ? 'Out' : 'In'
      return rates((change) => `${degree}-degree: ${change}`)
    }
    case 'fill_rate_drop':
      return rates((change) => change)
    case 'undeclared_value': {
      if (f.value === undefined) return f.detail
      const change = valueChange(f.value, f.count)
      return f.share === undefined ? change : `${change} (${formatPercent(f.share)})`
    }
    case 'undeclared':
    case 'vanished':
      return f.detail
  }
}

/** `0.5% → 3% (+2.5 pts)`: a ratio's change, in percentage points. */
export function rateChange(baseline: number, observed: number): string {
  return `${formatPercent(baseline)} → ${formatPercent(observed)} (${formatPoints(observed - baseline, { signed: true })})`
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
