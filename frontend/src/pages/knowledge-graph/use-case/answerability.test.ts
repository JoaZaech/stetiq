import { describe, expect, it } from 'vitest'
import type { EvaluationResult } from '@/api/ontology-versions'
import { answerabilityOf } from './answerability'

const result = (fields: Partial<EvaluationResult>): EvaluationResult => ({
  knowledge_graph: 'support',
  subject_kind: 'ontology_version',
  subject_id: '3',
  evaluator: 'structural_answerability',
  metrics: {},
  details: [],
  created_at: '2026-01-01T00:00:00',
  parameters: {},
  use_case_version: 2,
  ...fields,
})

const JUDGED = result({
  metrics: { questions: 2, answerable_questions: 1 },
  details: [
    {
      item: 'refunds',
      message: 'missing Refund',
      metric: 'unanswerable_questions',
      data: { status: 'unanswerable', missing: ['Refund'] },
    },
    {
      item: 'customer-names',
      message: 'answerable',
      metric: 'answerable_questions',
      data: { status: 'answerable', missing: [] },
    },
  ],
})

describe('answerabilityOf', () => {
  it('reads the structural answerability judged against the Use Case Version', () => {
    expect(answerabilityOf([result({ evaluator: 'concept_count' }), JUDGED], 2)).toEqual({
      questions: 2,
      answerable: 1,
      rows: [
        { id: 'customer-names', status: 'answerable', missing: [] },
        { id: 'refunds', status: 'unanswerable', missing: ['Refund'] },
      ],
    })
  })

  it('finds nothing when the result was judged against another Use Case Version', () => {
    expect(answerabilityOf([JUDGED], 3)).toBeUndefined()
  })
})
