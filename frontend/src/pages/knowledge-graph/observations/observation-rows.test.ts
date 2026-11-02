import { describe, expect, it } from 'vitest'
import type { AlignmentPoint, DriftEvent, Observation } from '@/api/observations'
import { filterObservationRows, formatThresholds, notComparableRows, observationRows } from './observation-rows'

const observation = (id: string, run_id: string | null = null, baseline: string | null = null): Observation => ({
  id,
  knowledge_graph: 'support',
  run_id,
  observed_at: '2026-11-02T10:00:00Z',
  scope: { database: 'neo4j', label: null, namespace: null },
  baseline_observation_id: baseline,
  not_comparable: [],
  conformance: null,
  ontology_version: null,
})

const drift: DriftEvent = {
  id: 'd1',
  knowledge_graph: 'support',
  observation_id: 'o2',
  previous_observation_id: 'o1',
  contract_alias: 'production',
  ontology_version: 3,
  detected_at: '2026-11-02T10:00:00Z',
  findings: [
    { kind: 'undeclared', subject: 'Refund', subject_kind: 'node_type', detail: '', previous_count: null, observed_count: null },
  ],
  thresholds: { max_count_drop: null, max_count_increase: 0.5, max_violation_increase: 0.01 },
}

describe('observationRows', () => {
  const rows = observationRows([observation('o1', 'run-abc'), observation('o2', null, 'o1')], [drift])

  it('puts the newest first and counts its findings', () => {
    expect(rows.map((r) => [r.observation.id, r.status, r.findings])).toEqual([
      ['o2', 'Drift', 1],
      ['o1', 'No Drift', 0],
    ])
  })

  it('links each on-demand Observation to its Baseline Observation', () => {
    expect(rows.map((r) => r.baseline?.id)).toEqual(['o1', undefined])
  })

  it('filters by status and by run id, version or Contract Alias', () => {
    expect(filterObservationRows(rows, '', 'No Drift').map((r) => r.observation.id)).toEqual(['o1'])
    expect(filterObservationRows(rows, 'run-abc', '').map((r) => r.observation.id)).toEqual(['o1'])
    expect(filterObservationRows(rows, 'production v3', '').map((r) => r.observation.id)).toEqual(['o2'])
  })
})

describe('observationRows with the alignment trend', () => {
  const scored: AlignmentPoint = {
    at: '2026-11-02T10:00:00Z',
    score: 0.5,
    ontology_version: 3,
    observation_id: 'o2',
    run_id: null,
  }

  it('gives a scored Observation its point, and an older one none', () => {
    const rows = observationRows([observation('o1'), observation('o2')], [], [scored])
    expect(rows.map((r) => [r.observation.id, r.alignment?.score])).toEqual([
      ['o2', 0.5],
      ['o1', undefined],
    ])
  })
})

describe('formatThresholds', () => {
  it('names each threshold, off when not set', () => {
    expect(formatThresholds(drift.thresholds)).toBe('max drop off · max rise 50% · max violation rise 1 pt')
  })

  it('reads an event from before Violation Rates as that check off', () => {
    expect(formatThresholds({ max_count_drop: 0.1, max_count_increase: null })).toBe(
      'max drop 10% · max rise off · max violation rise off',
    )
  })
})

describe('notComparableRows', () => {
  it('names the check and its subject, sorted by subject', () => {
    expect(
      notComparableRows([
        { check: 'undeclared_value', subject: 'WorkOrder.status', subject_kind: 'property', reason: 'value list truncated' },
        {
          check: 'violation_increase',
          subject: 'Customer.name',
          subject_kind: 'property',
          reason: 'no Violation Rate in the Baseline Observation',
          violation: 'required_missing',
        },
      ]),
    ).toEqual([
      {
        subject: 'Customer.name',
        kind: 'Attribute',
        check: 'Violation Rate: Required but not always set',
        reason: 'no Violation Rate in the Baseline Observation',
      },
      { subject: 'WorkOrder.status', kind: 'Attribute', check: 'Value outside the Vocabulary', reason: 'value list truncated' },
    ])
  })
})
