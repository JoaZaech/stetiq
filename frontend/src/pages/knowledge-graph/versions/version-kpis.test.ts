import { describe, expect, it } from 'vitest'
import type { GateResult } from '@/api/gate-results'
import type { ConstructionRun } from '@/api/runs'
import { versionEvaluationInputs, versionMatches } from './version-kpis'

const run = (candidate_version: number | null, score: number | null): ConstructionRun => ({
  id: 'r',
  knowledge_graph: 'support',
  ontology_version: 1,
  status: 'finished',
  started_at: '2026-11-02T10:00:00Z',
  ended_at: null,
  params: {},
  metrics: {},
  observation_id: null,
  conformance: score === null ? null : { score, mismatches: [] },
  candidate_version,
})

const gate = (passed: boolean[]): GateResult => ({
  knowledge_graph: 'support',
  subject_kind: 'ontology_version',
  subject_id: '2',
  ontology_version: 2,
  passed: passed.every(Boolean),
  outcomes: passed.map((p, i) => ({ gate: { name: `g${i}` }, passed: p, reasons: [] })),
  evaluated_at: '2026-11-02T10:00:00Z',
})

describe('versionEvaluationInputs', () => {
  it('takes Conformance from the run that gave rise to the version, and counts Gates passed', () => {
    expect(
      versionEvaluationInputs(2, [run(1, 0.5), run(2, 0.9)], { questions: 9, answerable: 2, rows: [] }, gate([true, false])),
    ).toEqual({ conformance: 0.9, coverage: { count: 2, total: 9 }, gates: { count: 1, total: 2 }, drift: null })
  })

  it('leaves what it does not know as null', () => {
    expect(versionEvaluationInputs(2, undefined, undefined, undefined)).toEqual({
      conformance: null,
      coverage: null,
      gates: null,
      drift: null,
    })
  })
})

describe('versionMatches', () => {
  it('matches the number, origin and Aliases', () => {
    const row = { number: 3, origin: 'run', aliases: ['production'] }
    expect(versionMatches(row, 'v3')).toBe(true)
    expect(versionMatches(row, 'prod')).toBe(true)
    expect(versionMatches(row, 'staging')).toBe(false)
  })
})
