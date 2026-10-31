import { describe, expect, it } from 'vitest'
import type { EvaluationResult } from '@/api/ontology-versions'
import { evaluatorMetrics } from './evaluator-metrics'

function result(
  evaluator: string,
  metrics: Record<string, number>,
  parameters: Record<string, unknown> = {},
): EvaluationResult {
  return {
    knowledge_graph: 'support',
    subject_kind: 'ontology_version',
    subject_id: '1',
    evaluator,
    metrics,
    details: [],
    created_at: '2026-10-30T12:00:00+00:00',
    parameters,
    use_case_version: null,
  }
}

describe('evaluatorMetrics', () => {
  it('names each metric after its Evaluator', () => {
    expect(
      evaluatorMetrics([
        result('hierarchy', { max_depth: 2, orphans: 0 }),
        result('structural_answerability', { answerable_ratio: 0.5 }),
      ]),
    ).toEqual({
      'hierarchy/max_depth': 2,
      'hierarchy/orphans': 0,
      'structural_answerability/answerable_ratio': 0.5,
    })
  })

  it('keeps results of one Evaluator with different parameters apart', () => {
    expect(
      evaluatorMetrics([
        result('coverage', { ratio: 0.5 }, { min: 1 }),
        result('coverage', { ratio: 0.25 }, { min: 2 }),
      ]),
    ).toEqual({
      'coverage (min=1)/ratio': 0.5,
      'coverage (min=2)/ratio': 0.25,
    })
  })

  it('names parameters in key order, however the result lists them', () => {
    expect(evaluatorMetrics([result('coverage', { ratio: 0.5 }, { min: 1, gold: 'v2' })])).toEqual({
      'coverage (gold="v2", min=1)/ratio': 0.5,
    })
  })
})
