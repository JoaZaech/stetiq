import type { CompetencyQuestion, UseCase } from '@/api/use-cases'

/** The Competency Question form's fields, as typed (all text). */
export interface QuestionDraft {
  id: string
  question: string
  /** Cypher; blank = none. */
  query: string
  /** JSON; blank = none. */
  expected_answer: string
  /** Concept references, one per line (or comma-separated); blank = none. */
  concepts: string
}

export type DraftField = keyof QuestionDraft
export type DraftErrors = Partial<Record<DraftField, string>>

export const EMPTY_DRAFT: QuestionDraft = {
  id: '',
  question: '',
  query: '',
  expected_answer: '',
  concepts: '',
}

/** The form, filled in from an existing question. */
export function draftOf(question: CompetencyQuestion): QuestionDraft {
  return {
    id: question.id,
    question: question.question,
    query: question.query ?? '',
    expected_answer:
      question.expected_answer === undefined ? '' : JSON.stringify(question.expected_answer, null, 2),
    concepts: (question.concepts ?? []).join('\n'),
  }
}

/** The Competency Question a draft describes; unset fields are omitted, as the wire does. */
export function questionOf(draft: QuestionDraft): CompetencyQuestion {
  const question: CompetencyQuestion = { id: draft.id.trim(), question: draft.question.trim() }
  if (draft.query.trim()) question.query = draft.query.trim()
  if (draft.expected_answer.trim()) question.expected_answer = JSON.parse(draft.expected_answer)
  const concepts = splitConcepts(draft.concepts)
  if (concepts.length) question.concepts = concepts
  return question
}

function splitConcepts(text: string): string[] {
  return text
    .split(/[\n,]/)
    .map((c) => c.trim())
    .filter(Boolean)
}

/** `useCase` with `question` added, or replacing the one with its id; questions sorted by id. */
export function withQuestion(useCase: UseCase, question: CompetencyQuestion): UseCase {
  const others = useCase.competency_questions.filter((q) => q.id !== question.id)
  return {
    ...useCase,
    competency_questions: [...others, question].sort((a, b) => a.id.localeCompare(b.id)),
  }
}

/** `useCase` without the question `id`. */
export function withoutQuestion(useCase: UseCase, id: string): UseCase {
  return { ...useCase, competency_questions: useCase.competency_questions.filter((q) => q.id !== id) }
}
