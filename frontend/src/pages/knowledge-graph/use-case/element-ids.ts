import type { UseCase } from '@/api/use-cases'

/**
 * What already holds `id` in the Use Case, other than `own` (the id being edited):
 * Consumer, Task and Competency Question ids are unique across the whole Use Case.
 */
function holderOf(useCase: UseCase, id: string, own: string | undefined): string | undefined {
  if (id === own) return undefined
  if (useCase.competency_questions.some((q) => q.id === id)) return `The Competency Question ${id}`
  for (const consumer of useCase.consumers ?? []) {
    if (consumer.id === id) return `The Consumer ${id}`
    if ((consumer.tasks ?? []).some((t) => t.id === id)) return `The Task ${id}`
  }
  return undefined
}

/** The error for an element id typed into a form: missing, or held by another element. */
export function checkId(id: string, useCase: UseCase, own: string | undefined): string | undefined {
  if (!id) return 'Needs an id.'
  const holder = holderOf(useCase, id, own)
  return holder && `${holder} already has this id.`
}
