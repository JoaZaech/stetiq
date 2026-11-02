import { describe, expect, it } from 'vitest'
import type { DriftFinding } from '@/api/observations'
import type { Mismatch } from '@/api/runs'
import { countChange, facetCounts, filterFindings, findingsFromDrift, findingsFromMismatches } from './findings'

const mismatch = (m: Partial<Mismatch>): Mismatch => ({
  subject: 'Sensor',
  subject_kind: 'node_type',
  kind: 'undeclared',
  detail: '',
  ...m,
})

const drift = (f: Partial<DriftFinding>): DriftFinding => ({
  kind: 'count_drop',
  subject: 'FollowUp',
  subject_kind: 'node_type',
  detail: 'count dropped from 12 to 6 (-50%)',
  previous_count: 12,
  observed_count: 6,
  ...f,
})

describe('findingsFromMismatches', () => {
  it('names each mismatch, sorted by finding then subject', () => {
    const rows = findingsFromMismatches([
      mismatch({ subject: 'Sensor.unit', subject_kind: 'property' }),
      mismatch({ subject: '(Machine)-[HAS_SENSOR]->(Sensor)', subject_kind: 'pattern' }),
      mismatch({ subject: 'Ticket', kind: 'absent', detail: 'never observed' }),
    ])
    expect(rows.map((r) => [r.subject, r.kind, r.finding, r.change])).toEqual([
      ['Ticket', 'Class', 'Declared but not observed', 'never observed'],
      ['(Machine)-[HAS_SENSOR]->(Sensor)', 'Pattern', 'Observed but not declared', ''],
      ['Sensor.unit', 'Attribute', 'Observed but not declared', ''],
    ])
  })

  it('shows a value mismatch as the value and its count; a deprecated value is neutral', () => {
    const [row] = findingsFromMismatches([mismatch({ kind: 'deprecated_value', value: 'old', count: 3 })])
    expect(row.change).toBe('“old” × 3')
    expect(row.tone).toBe('neutral')
  })
})

describe('findingsFromDrift', () => {
  it('shows a count change as before → after with its percentage', () => {
    expect(findingsFromDrift([drift({})])[0]).toMatchObject({
      finding: 'Count dropped',
      change: '12 → 6 (−50%)',
      tone: 'warning',
    })
  })

  it('falls back to the value, then the detail', () => {
    const rows = findingsFromDrift([
      drift({ kind: 'undeclared_value', previous_count: null, observed_count: null, value: 'x', subject: 'A' }),
      drift({ kind: 'undeclared', previous_count: null, observed_count: null, detail: '', subject: 'B' }),
    ])
    expect(rows.map((r) => r.change)).toEqual(['', '“x”'])
  })

  it('shows an undeclared value with its count and its share of the owner, when known', () => {
    const rows = findingsFromDrift([
      drift({ kind: 'undeclared_value', previous_count: null, observed_count: null, value: 'x', count: 2, share: 0.25 }),
      drift({ kind: 'undeclared_value', previous_count: null, observed_count: null, value: 'y', count: 3, subject: 'B' }),
    ])
    expect(rows.map((r) => r.change)).toEqual(['“y” × 3', '“x” × 2 (25%)'])
  })

  it('shows a risen Violation Rate as baseline → now, on its Attribute or pattern', () => {
    const rows = findingsFromDrift([
      drift({
        kind: 'violation_increase',
        subject: 'Customer.name',
        subject_kind: 'property',
        previous_count: null,
        observed_count: null,
        violation: 'required_missing',
        baseline_rate: 0.005,
        observed_rate: 0.03,
      }),
      drift({ kind: 'violation_increase', subject: '(A)-[R]->(B)', subject_kind: 'pattern', previous_count: null, observed_count: null }),
    ])
    expect(rows.map((r) => [r.kind, r.finding, r.change])).toEqual([
      ['Pattern', 'Violation Rate rose', 'count dropped from 12 to 6 (-50%)'],
      ['Attribute', 'Violation Rate rose', 'Required but not always set: 0.5% → 3% (+2.5 pts)'],
    ])
  })
})

describe('countChange', () => {
  it('has no percentage from zero', () => {
    expect(countChange(0, 4)).toBe('0 → 4')
    expect(countChange(1, 4)).toBe('1 → 4 (+300%)')
  })
})

describe('filterFindings and facetCounts', () => {
  const rows = findingsFromMismatches([
    mismatch({ subject: 'Sensor' }),
    mismatch({ subject: 'Sensor.unit', subject_kind: 'property' }),
    mismatch({ subject: 'Ticket', kind: 'absent' }),
  ])

  it('filters by kind, finding and search', () => {
    expect(filterFindings(rows, { kind: 'Class', finding: '', query: '' })).toHaveLength(2)
    expect(filterFindings(rows, { kind: '', finding: 'Observed but not declared', query: 'unit' })).toHaveLength(1)
  })

  it('counts each value, most first', () => {
    expect(facetCounts(rows, 'kind')).toEqual([
      ['Class', 2],
      ['Attribute', 1],
    ])
  })
})
