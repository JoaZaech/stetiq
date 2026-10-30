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

// Concept-reference syntax, as use_case/concepts.py `parse_concept_reference` reads it
// (`\x60` is a backtick).
const IDENT = String.raw`[^\s()\[\]{}.:|\x60,-][^\s()\[\]{}.:|\x60,]*`
const LABEL_RE = new RegExp(`^${IDENT}$`)
const PROPERTY_RE = new RegExp(`^${IDENT}\\.${IDENT}$`)
const PATH_RE = new RegExp(
  String.raw`^\((?:${IDENT})?\)(<)?-\[(?:${IDENT}(?:\|${IDENT})*)?\]-(>)?\((?:${IDENT})?\)$`,
)

/** `Label`, `Owner.property` or `(Source)-[REL]->(Target)` (one direction at most). */
export function isConceptReference(text: string): boolean {
  const ref = text.trim()
  if (LABEL_RE.test(ref) || PROPERTY_RE.test(ref)) return true
  const path = PATH_RE.exec(ref)
  return path !== null && !(path[1] && path[2])
}

/**
 * The form's errors, per field, before anything is sent: a missing id or question, an
 * id another question in the Use Case has (`otherIds`), an expected answer that is not
 * JSON, malformed Concept references. Empty when the draft can be saved.
 */
export function validateDraft(draft: QuestionDraft, otherIds: readonly string[]): DraftErrors {
  const errors: DraftErrors = {}
  const id = draft.id.trim()
  if (!id) errors.id = 'Needs an id.'
  else if (otherIds.includes(id)) errors.id = `Another Competency Question already has the id ${id}.`
  if (!draft.question.trim()) errors.question = 'Needs the question in natural language.'
  if (draft.expected_answer.trim()) {
    try {
      JSON.parse(draft.expected_answer)
    } catch (error) {
      errors.expected_answer = `Not valid JSON: ${(error as Error).message}`
    }
  }
  const malformed = splitConcepts(draft.concepts).filter((c) => !isConceptReference(c))
  if (malformed.length) {
    errors.concepts = `Not a Concept reference: ${malformed.map((c) => JSON.stringify(c)).join(', ')}.`
  }
  return errors
}

const SERVER_FIELD_RE = /^[^:]*?\.(id|question|query|expected_answer|concepts): /

/**
 * The form field a server Use Case validation error is about (`<path>.<field>: ...`, or
 * `<id>: duplicate competency question id`); undefined when it is about the whole Use Case.
 */
export function serverErrorField(message: string): DraftField | undefined {
  if (/: duplicate competency question id$/.test(message)) return 'id'
  return SERVER_FIELD_RE.exec(message)?.[1] as DraftField | undefined
}

/** `useCase` without the question `id`. */
export function withoutQuestion(useCase: UseCase, id: string): UseCase {
  return { ...useCase, competency_questions: useCase.competency_questions.filter((q) => q.id !== id) }
}
