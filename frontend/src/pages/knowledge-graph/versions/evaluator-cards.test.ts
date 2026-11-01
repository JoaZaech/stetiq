import { describe, expect, it } from 'vitest'
import type { EvaluationResult } from '@/api/ontology-versions'
import { EVALUATOR_DISPLAY, evaluatorCard, evaluatorCards } from './evaluator-cards'

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

describe('EVALUATOR_DISPLAY', () => {
  it('covers every built-in Evaluator, the version and the run ones', () => {
    expect(Object.keys(EVALUATOR_DISPLAY).sort()).toEqual([
      'competency_question_coverage',
      'competency_question_execution',
      'conformance',
      'constraint_consistency',
      'definitions',
      'hierarchy',
      'isolated_node_types',
      'observed_schema',
      'orphan_concepts',
      'redundancy',
      'structural_answerability',
    ])
  })
})

describe('evaluatorCard', () => {
  it('titles a built-in Evaluator readably, with its tooltip and headline metrics', () => {
    expect(
      evaluatorCard(
        result('structural_answerability', {
          questions: 6,
          answerable_questions: 5,
          unanswerable_questions: 1,
          answerable_ratio: 0.8333,
        }),
      ),
    ).toEqual({
      evaluator: 'structural_answerability',
      title: 'Answerable questions',
      tooltip: expect.stringContaining('Competency Questions') as string,
      headlines: [
        { metric: 'answerable_questions', label: 'Answerable', value: '5 / 6' },
        { metric: 'unanswerable_questions', label: 'Unanswerable', value: '1' },
      ],
      useCaseVersion: null,
    })
  })

  it('shows ratios as percentages', () => {
    expect(evaluatorCard(result('definitions', { definition_ratio: 0.7097, concepts_without_definition: 9 })).headlines).toEqual([
      { metric: 'definition_ratio', label: 'Defined', value: '71%' },
    ])
    expect(evaluatorCard(result('conformance', { score: 0.8889, mismatches: 2 })).headlines).toEqual([
      { metric: 'score', label: 'Score', value: '88.9%' },
      { metric: 'mismatches', label: 'Mismatches', value: '2' },
    ])
  })

  it('titles an Evaluator outside the map by its raw name and shows its first metric', () => {
    const card = evaluatorCard(result('report_coverage', { covered: 0.5, missing: 3 }, { min: 1 }))
    expect(card).toMatchObject({
      evaluator: 'report_coverage (min=1)',
      title: 'report_coverage (min=1)',
      tooltip: null,
      headlines: [{ metric: 'covered', label: 'covered', value: '0.5' }],
    })
  })

  it('keeps a built-in’s parameters in its title, and falls back to its first metric when its headlines are missing', () => {
    const card = evaluatorCard(result('hierarchy', { max_breadth: 4 }, { variant: 'b' }))
    expect(card.title).toBe('Class hierarchy (variant="b")')
    expect(card.headlines).toEqual([{ metric: 'max_breadth', label: 'max_breadth', value: '4' }])
  })
})

describe('evaluatorCards', () => {
  it('orders the built-in Evaluators as the map does, then the others by name', () => {
    expect(
      evaluatorCards([
        result('review', { score: 0.9 }),
        result('hierarchy', { max_depth: 2 }),
        result('accuracy', { score: 1 }),
        result('structural_answerability', { questions: 1, answerable_questions: 1 }),
      ]).map((card) => card.title),
    ).toEqual(['Answerable questions', 'Class hierarchy', 'accuracy', 'review'])
  })
})
