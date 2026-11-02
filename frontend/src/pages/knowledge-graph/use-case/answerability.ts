import type { EvaluationResult } from '@/api/ontology-versions'
import type { StatusTone } from '@/components/status-tones'

/** evaluation/answerability.py `ANSWERABILITY_EVALUATOR`. */
export const ANSWERABILITY_EVALUATOR = 'structural_answerability'

export type AnswerabilityStatus = 'answerable' | 'unanswerable' | 'unmapped'

/**
 * How the UI shows each status. *Unmapped* reads as the neutral "Can't check": stetiq
 * cannot tell, which is neither a pass nor a failure.
 */
export const ANSWERABILITY_LABELS: Record<AnswerabilityStatus, { tone: StatusTone; label: string; hint?: string }> = {
  answerable: { tone: 'success', label: 'Answerable' },
  unanswerable: { tone: 'failure', label: 'Unanswerable' },
  unmapped: { tone: 'neutral', label: "Can't check", hint: "No Concept mapping or query, so stetiq can't tell" },
}

export interface Answerability {
  questions: number
  answerable: number
  /** One per Competency Question, sorted by id. */
  rows: AnswerabilityRow[]
}

export interface AnswerabilityRow {
  /** The Competency Question's id. */
  id: string
  status: AnswerabilityStatus
  /** The Concepts an unanswerable question needs and the Ontology Version lacks. */
  missing: string[]
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
    // A regressed question also has its own Detail; it is not a second row.
    rows: result.details
      .filter((d) => d.metric !== 'regressed_questions')
      .map((d) => ({
        id: d.item,
        status: (d.data?.status ?? 'unmapped') as AnswerabilityStatus,
        missing: (d.data?.missing as string[] | undefined) ?? [],
      }))
      .sort((a, b) => a.id.localeCompare(b.id)),
  }
}
