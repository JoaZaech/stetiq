import type { EvaluationResult } from '@/api/ontology-versions'

/** evaluation/answerability.py `ANSWERABILITY_EVALUATOR`. */
export const ANSWERABILITY_EVALUATOR = 'structural_answerability'

export type AnswerabilityStatus = 'answerable' | 'unanswerable' | 'unmapped'

export interface Answerability {
  questions: number
  answerable: number
  /** One per Competency Question, sorted by id. */
  rows: { id: string; status: AnswerabilityStatus; missing: string[] }[]
}

/**
 * The structural answerability among an Ontology Version's Evaluator results that was
 * judged against `useCaseVersion`; undefined if none was.
 */
export function answerabilityOf(
  results: readonly EvaluationResult[],
  useCaseVersion: number,
): Answerability | undefined {
  const result = results.find(
    (r) => r.evaluator === ANSWERABILITY_EVALUATOR && r.use_case_version === useCaseVersion,
  )
  if (!result) return undefined
  return {
    questions: result.metrics.questions ?? 0,
    answerable: result.metrics.answerable_questions ?? 0,
    rows: result.details
      .map((d) => ({
        id: d.item,
        status: (d.data?.status ?? 'unmapped') as AnswerabilityStatus,
        missing: (d.data?.missing as string[] | undefined) ?? [],
      }))
      .sort((a, b) => a.id.localeCompare(b.id)),
  }
}
