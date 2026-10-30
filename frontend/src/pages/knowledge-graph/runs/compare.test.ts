import { describe, expect, it } from 'vitest'
import type { EvaluationResult } from '@/api/ontology-versions'
import type { ConstructionRun } from '@/api/runs'
import { compareRuns, differs, runChartPoints } from './compare'

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

function evaluation(evaluator: string, metrics: Record<string, number>): EvaluationResult {
  return {
    knowledge_graph: 'support',
    subject_kind: 'construction_run',
    subject_id: 'r',
    evaluator,
    metrics,
    details: [],
    created_at: '2026-10-30T11:01:00Z',
    parameters: {},
    use_case_version: null,
  }
}

describe('compareRuns', () => {
  const a = run({
    id: 'a',
    params: { extractor: 'llm', temperature: '0.2' },
    metrics: { recall: 0.8, precision: 0.91 },
    conformance: { score: 0.5, mismatches: [] },
  })
  const b = run({
    id: 'b',
    ontology_version: 2,
    params: { extractor: 'llm', batch: '10' },
    metrics: { recall: 0.8 },
  })

  it('puts each param and metric key on one row, sorted, with a value per run (null where not logged)', () => {
    const comparison = compareRuns([a, b], [[], []])
    expect(comparison.params).toEqual([
      { key: 'batch', values: [null, '10'] },
      { key: 'extractor', values: ['llm', 'llm'] },
      { key: 'temperature', values: ['0.2', null] },
    ])
    expect(comparison.metrics).toEqual([
      { key: 'precision', values: [0.91, null] },
      { key: 'recall', values: [0.8, 0.8] },
    ])
  })

  it('compares the Declared Ontology, Candidate and Conformance score of each run', () => {
    const comparison = compareRuns([a, b], [[], []])
    expect(comparison.declaredOntology).toEqual([1, 2])
    expect(comparison.candidate).toEqual([null, null])
    expect(comparison.conformance).toEqual([0.5, null])
  })

  it('keys Evaluator metrics `<evaluator>/<metric>`, as the version table does', () => {
    const comparison = compareRuns(
      [a, b],
      [[evaluation('conformance', { score: 0.5 })], [evaluation('conformance', { score: 0.7 }), evaluation('observed_schema', { node_types: 2 })]],
    )
    expect(comparison.evaluations).toEqual([
      { key: 'conformance/score', values: [0.5, 0.7] },
      { key: 'observed_schema/node_types', values: [null, 2] },
    ])
  })
})

describe('differs', () => {
  it('is false when every run has the same value, missing ones included', () => {
    expect(differs(['llm', 'llm', 'llm'])).toBe(false)
    expect(differs([null, null])).toBe(false)
  })

  it('is true when any value differs, or one run lacks it', () => {
    expect(differs([0.8, 0.9])).toBe(true)
    expect(differs(['llm', null])).toBe(true)
  })
})

describe('runChartPoints', () => {
  it('plots each run at its start time with its metrics and Conformance score', () => {
    const points = runChartPoints([
      run({ started_at: '2026-10-30T11:00:00Z', metrics: { recall: 0.8 }, conformance: { score: 0.5, mismatches: [] } }),
      run({ started_at: '2026-10-30T12:00:00Z', metrics: { recall: 0.9 } }),
    ])
    expect(points).toEqual([
      { x: Date.parse('2026-10-30T11:00:00Z'), metrics: { recall: 0.8, Conformance: 0.5 } },
      { x: Date.parse('2026-10-30T12:00:00Z'), metrics: { recall: 0.9 } },
    ])
  })
})
