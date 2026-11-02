import { describe, expect, it } from 'vitest'
import type { GatePreview } from '@/api/gate-previews'
import type { GateResult } from '@/api/gate-results'
import type { DriftEvent } from '@/api/observations'
import type { EvaluationResult } from '@/api/ontology-versions'
import type { ConstructionRun } from '@/api/runs'
import {
  conformanceTone,
  CQ_EXECUTION_EVALUATOR,
  filterRuns,
  formatDuration,
  parseRunFilters,
  runEvaluationInputs,
  runFailure,
  runGate,
  runKeys,
  runOutcome,
  runSearchFields,
  sourceList,
  splitParamKeys,
} from './runs'

const NOW = Date.parse('2026-10-30T12:00:00Z')

function run(overrides: Partial<ConstructionRun>): ConstructionRun {
  return {
    id: 'r',
    knowledge_graph: 'support',
    ontology_version: 1,
    status: 'finished',
    started_at: '2026-10-30T11:00:00Z',
    ended_at: '2026-10-30T11:01:00Z',
    params: {},
    metrics: {},
    observation_id: 'o',
    conformance: null,
    candidate_version: null,
    ...overrides,
  }
}

describe('filterRuns', () => {
  const recent = run({ id: 'recent', status: 'failed', started_at: '2026-10-30T02:00:00Z' })
  const lastWeek = run({ id: 'last-week', started_at: '2026-10-25T12:00:00Z' })
  const old = run({ id: 'old', started_at: '2026-01-01T00:00:00Z' })
  const runs = [recent, lastWeek, old]
  const ids = (filtered: ConstructionRun[]) => filtered.map((r) => r.id)

  it('keeps every run without filters', () => {
    expect(ids(filterRuns(runs, { status: 'all', range: 'all' }, NOW))).toEqual(['recent', 'last-week', 'old'])
  })

  it('keeps the runs started within the time range', () => {
    expect(ids(filterRuns(runs, { status: 'all', range: '24h' }, NOW))).toEqual(['recent'])
    expect(ids(filterRuns(runs, { status: 'all', range: '7d' }, NOW))).toEqual(['recent', 'last-week'])
  })

  it('keeps the runs with the status', () => {
    expect(ids(filterRuns(runs, { status: 'finished', range: 'all' }, NOW))).toEqual(['last-week', 'old'])
    expect(ids(filterRuns(runs, { status: 'failed', range: '7d' }, NOW))).toEqual(['recent'])
  })
})

describe('parseRunFilters', () => {
  it('reads the filters from the URL and treats unknown values as all', () => {
    expect(parseRunFilters(new URLSearchParams('status=failed&range=7d'))).toEqual({
      status: 'failed',
      range: '7d',
    })
    expect(parseRunFilters(new URLSearchParams('status=done&range=1y'))).toEqual({ status: 'all', range: 'all' })
  })
})

describe('runOutcome', () => {
  it('tells a strict Evolution Mode failure from a run that failed before observing', () => {
    expect(runOutcome(run({ status: 'failed', observation_id: 'o' }))).toBe('strict')
    expect(runOutcome(run({ status: 'failed', observation_id: null }))).toBe('failed')
    expect(runOutcome(run({ status: 'finished' }))).toBe('finished')
    expect(runOutcome(run({ status: 'running', ended_at: null, observation_id: null }))).toBe('running')
  })
})

describe('formatDuration', () => {
  it('uses the largest sensible unit', () => {
    expect(formatDuration(850)).toBe('850 ms')
    expect(formatDuration(4_200)).toBe('4.2 s')
    expect(formatDuration(184_000)).toBe('3 min 4 s')
    expect(formatDuration(7_500_000)).toBe('2 h 5 min')
  })
})

describe('runKeys', () => {
  it('lists every param and metric key once, sorted', () => {
    const runs = [
      run({ params: { temperature: '0.2', extractor: 'llm' }, metrics: { recall: 0.8 } }),
      run({ params: { extractor: 'rules' }, metrics: { precision: 0.9 } }),
    ]
    expect(runKeys(runs)).toEqual({ params: ['extractor', 'temperature'], metrics: ['precision', 'recall'] })
  })
})

describe('splitParamKeys', () => {
  it('shows extractor, model and sources as columns, in that order, and leaves the rest to Columns', () => {
    expect(splitParamKeys(['batch', 'extractor', 'sources', 'temperature'])).toEqual({
      shown: ['extractor', 'sources'],
      optional: ['batch', 'temperature'],
    })
    expect(splitParamKeys([])).toEqual({ shown: [], optional: [] })
  })
})

describe('sourceList', () => {
  it('splits a sources param on commas, dropping blanks', () => {
    expect(sourceList('machines.csv, material_flow.json,  reports/,')).toEqual([
      'machines.csv',
      'material_flow.json',
      'reports/',
    ])
  })
})

describe('runSearchFields', () => {
  it('searches the id, param values and versions', () => {
    expect(runSearchFields(run({ id: 'abc', params: { model: 'opus' }, candidate_version: 2 }))).toEqual([
      'abc',
      'opus',
      'v1',
      'v2',
    ])
  })
})

describe('runFailure', () => {
  it('says why a run failed in one line, and which findings show it', () => {
    expect(runFailure(run({ status: 'finished' }))).toBeNull()
    expect(runFailure(run({ status: 'failed', observation_id: null }))).toEqual({
      text: 'Failed before the Graph Source was observed.',
      finding: null,
    })
    const mismatch = (subject: string, subject_kind: 'node_type' | 'pattern') =>
      ({ subject, subject_kind, kind: 'undeclared', detail: '' }) as const
    expect(
      runFailure(
        run({
          status: 'failed',
          conformance: { score: 0.9, mismatches: [mismatch('Sensor', 'node_type'), mismatch('(A)-[R]->(B)', 'pattern')] },
        }),
      ),
    ).toEqual({ text: 'Failed: 1 Concept observed but not declared (strict mode).', finding: 'Observed but not declared' })
  })
})

describe('runEvaluationInputs', () => {
  const execution: EvaluationResult = {
    evaluator: CQ_EXECUTION_EVALUATOR,
    details: [
      { item: 'a', message: '', data: { status: 'passed', check: 'non_empty' } },
      { item: 'b', message: '', data: { status: 'error', check: 'non_empty', error: 'ValueError' } },
    ],
  } as unknown as EvaluationResult
  const gate = {
    subject_kind: 'construction_run',
    subject_id: 'r',
    passed: false,
    outcomes: [{ passed: true }, { passed: false }, { passed: true }],
    evaluated_at: '2026-10-30T11:02:00Z',
  } as unknown as GateResult
  const drift = { observation_id: 'o', findings: [{}, {}] } as unknown as DriftEvent

  it('reads the run’s Conformance, executed questions, Gate result and Drift', () => {
    expect(runEvaluationInputs(run({ conformance: { score: 0.8, mismatches: [] } }), [execution], [gate], [drift])).toEqual({
      conformance: 0.8,
      coverage: { count: 1, total: 2 },
      gates: { count: 2, total: 3 },
      drift: 2,
    })
  })

  it('has no Drift without an Observation, and 0 when the Observation found none', () => {
    expect(runEvaluationInputs(run({ observation_id: null }), [], [], [drift])).toMatchObject({
      conformance: null,
      coverage: null,
      gates: null,
      drift: null,
    })
    expect(runEvaluationInputs(run({ observation_id: 'other' }), [], [], [drift]).drift).toBe(0)
  })
})

describe('conformanceTone', () => {
  it('colours a score by how close it is to 100 %', () => {
    expect(conformanceTone(1)).toBe('success')
    expect(conformanceTone(0.95)).toBe('success')
    expect(conformanceTone(0.8889)).toBe('warning')
    expect(conformanceTone(0.8)).toBe('warning')
    expect(conformanceTone(0.5455)).toBe('failure')
  })
})

describe('runGate', () => {
  const result = (subjectId: string, passed: boolean, evaluatedAt: string, kind: GateResult['subject_kind'] = 'construction_run'): GateResult => ({
    knowledge_graph: 'support',
    subject_kind: kind,
    subject_id: subjectId,
    ontology_version: 1,
    passed,
    outcomes: [],
    evaluated_at: evaluatedAt,
  })
  const preview = (subjectId: string, passed: boolean): GatePreview => ({
    knowledge_graph: 'support',
    subject_kind: 'construction_run',
    subject_id: subjectId,
    ontology_version: 1,
    passed,
    outcomes: [],
    source: { subject_kind: 'construction_run', subject_id: 'base', evaluated_at: '2026-10-30T10:00:00Z' },
  })

  it('shows the latest recorded Gate result, which wins over a preview', () => {
    const results = [result('r', true, '2026-10-30T10:00:00Z'), result('r', false, '2026-10-30T11:00:00Z')]
    expect(runGate('r', results, [preview('r', true)])).toEqual({ kind: 'recorded', passed: false })
  })

  it('shows the Gate Preview of a run without a recorded Gate result', () => {
    const results = [result('other', true, '2026-10-30T10:00:00Z'), result('r', true, '2026-10-30T10:00:00Z', 'ontology_version')]
    expect(runGate('r', results, [preview('other', false), preview('r', false)])).toEqual({
      kind: 'preview',
      passed: false,
    })
  })

  it('shows none without either', () => {
    expect(runGate('r', [], [])).toEqual({ kind: 'none' })
    expect(runGate('r', [result('other', true, '2026-10-30T10:00:00Z')], [preview('other', true)])).toEqual({
      kind: 'none',
    })
  })
})
