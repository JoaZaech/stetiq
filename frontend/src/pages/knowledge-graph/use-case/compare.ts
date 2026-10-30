import type { CompetencyQuestion, UseCase } from '@/api/use-cases'

/** The fields of a Competency Question that can change; its `id` is what matches it. */
export const COMPETENCY_QUESTION_FIELDS = ['question', 'query', 'expected_answer', 'concepts'] as const
export type CompetencyQuestionField = (typeof COMPETENCY_QUESTION_FIELDS)[number]

/** How each field is labelled, in the question table and in a comparison. */
export const FIELD_LABELS: Record<CompetencyQuestionField, string> = {
  question: 'Question',
  query: 'Query',
  expected_answer: 'Expected answer',
  concepts: 'Concept mapping',
}

export interface FieldChange {
  field: CompetencyQuestionField
  before: unknown
  after: unknown
}

export interface ChangedQuestion {
  id: string
  /** Only the fields that differ, in `COMPETENCY_QUESTION_FIELDS` order. */
  fields: FieldChange[]
}

/** How a Use Case changed from one Use Case Version to another. Lists are sorted by id. */
export interface UseCaseComparison {
  /** Set only when the description differs. */
  description: { before: string | undefined; after: string | undefined } | undefined
  added: CompetencyQuestion[]
  changed: ChangedQuestion[]
  removed: CompetencyQuestion[]
}

/**
 * Compare two Use Cases, matching Competency Questions by id (the glossary: a changed
 * id is a removal plus an addition). Values compare as JSON, ignoring object key order;
 * a missing Concept mapping equals an empty one.
 */
export function compareUseCases(from: UseCase, to: UseCase): UseCaseComparison {
  const before = byId(from.competency_questions)
  const after = byId(to.competency_questions)
  const added: CompetencyQuestion[] = []
  const changed: ChangedQuestion[] = []
  const removed: CompetencyQuestion[] = []
  for (const [id, question] of after) {
    const old = before.get(id)
    if (!old) {
      added.push(question)
      continue
    }
    const fields = COMPETENCY_QUESTION_FIELDS.filter(
      (field) => canonical(fieldValue(old, field)) !== canonical(fieldValue(question, field)),
    ).map((field) => ({ field, before: old[field], after: question[field] }))
    if (fields.length > 0) changed.push({ id, fields })
  }
  for (const [id, question] of before) if (!after.has(id)) removed.push(question)
  return {
    description:
      from.description === to.description
        ? undefined
        : { before: from.description, after: to.description },
    added,
    changed,
    removed,
  }
}

function byId(questions: CompetencyQuestion[]): Map<string, CompetencyQuestion> {
  const sorted = [...questions].sort((a, b) => (a.id < b.id ? -1 : a.id > b.id ? 1 : 0))
  return new Map(sorted.map((q) => [q.id, q]))
}

function fieldValue(question: CompetencyQuestion, field: CompetencyQuestionField): unknown {
  return field === 'concepts' ? (question.concepts ?? []) : question[field]
}

/** JSON with object keys sorted, so equal values give equal strings. */
function canonical(value: unknown): string {
  return JSON.stringify(value, (_key, v: unknown) =>
    v && typeof v === 'object' && !Array.isArray(v)
      ? Object.fromEntries(Object.entries(v).sort(([a], [b]) => (a < b ? -1 : a > b ? 1 : 0)))
      : v,
  ) ?? 'undefined'
}
