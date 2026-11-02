import { describe, expect, it } from 'vitest'
import type { AlignmentPoint } from '@/api/observations'
import { alignmentSeries, alignmentByObservation } from './alignment-trend'

const runPoint: AlignmentPoint = {
  at: '2026-11-02T10:00:00Z',
  score: 1,
  ontology_version: 2,
  observation_id: 'o2',
  run_id: 'run-abc',
}
const onDemand: AlignmentPoint = {
  at: '2026-11-01T09:00:00Z',
  score: 0.75,
  ontology_version: 1,
  observation_id: 'o1',
  run_id: null,
}

describe('alignmentSeries', () => {
  const series = alignmentSeries([runPoint, onDemand])

  it('is one Conformance line, in time order', () => {
    expect(series.metric).toBe('Conformance')
    expect(series.points.map((p) => [p.x, p.value, p.id])).toEqual([
      [Date.parse('2026-11-01T09:00:00Z'), 0.75, 'o1'],
      [Date.parse('2026-11-02T10:00:00Z'), 1, 'o2'],
    ])
  })

  it('marks run points filled and on-demand points hollow, and names the version judged against', () => {
    expect(series.points.map((p) => [p.marker, p.detail])).toEqual([
      [{ hollow: true, label: 'on demand' }, 'v1'],
      [{ hollow: false, label: 'run' }, 'v2'],
    ])
  })

  it('is empty without points', () => {
    expect(alignmentSeries([]).points).toEqual([])
  })
})

describe('alignmentByObservation', () => {
  it('finds each scored Observation, and nothing for one without a score', () => {
    const scored = alignmentByObservation([runPoint, onDemand])
    expect(scored.get('o1')).toBe(onDemand)
    expect(scored.get('o2')).toBe(runPoint)
    expect(scored.get('old')).toBeUndefined()
  })
})
