import { describe, expect, it } from 'vitest'
import type { DriftEvent, Observation } from '@/api/observations'
import { filterObservationRows, formatThresholds, observationRows } from './observation-rows'

const observation = (id: string, run_id: string | null = null): Observation => ({
  id,
  knowledge_graph: 'support',
  run_id,
  observed_at: '2026-11-02T10:00:00Z',
  scope: { database: 'neo4j', label: null, namespace: null },
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
  thresholds: { max_count_drop: null, max_count_increase: 0.5 },
}

describe('observationRows', () => {
  const rows = observationRows([observation('o1', 'run-abc'), observation('o2')], [drift])

  it('puts the newest first and counts its findings', () => {
    expect(rows.map((r) => [r.observation.id, r.status, r.findings])).toEqual([
      ['o2', 'Drift', 1],
      ['o1', 'No Drift', 0],
    ])
  })

  it('filters by status and by run id, version or Contract Alias', () => {
    expect(filterObservationRows(rows, '', 'No Drift').map((r) => r.observation.id)).toEqual(['o1'])
    expect(filterObservationRows(rows, 'run-abc', '').map((r) => r.observation.id)).toEqual(['o1'])
    expect(filterObservationRows(rows, 'production v3', '').map((r) => r.observation.id)).toEqual(['o2'])
  })
})

describe('formatThresholds', () => {
  it('names each threshold, off when not set', () => {
    expect(formatThresholds(drift.thresholds)).toBe('max drop off · max rise 50%')
  })
})
