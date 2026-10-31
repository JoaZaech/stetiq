import type { Task, UseCase } from '@/api/use-cases'
import type { Answerability } from './answerability'

/** How many of the Competency Questions a Task needs an Ontology Version can answer. */
export interface TaskReadiness {
  /** The questions the Task needs. */
  total: number
  answerable: number
  /** Mapped onto the Ontology, but Concepts or paths are missing. */
  unanswerable: number
  /** Nothing maps them onto the Ontology, so they are not judged answerable. */
  unmapped: number
}

/** A Task's readiness, rolled up from a stored structural answerability result. */
export function taskReadiness(task: Task, answerability: Answerability): TaskReadiness {
  const status = new Map(answerability.rows.map((row) => [row.id, row.status]))
  const readiness: TaskReadiness = { total: 0, answerable: 0, unanswerable: 0, unmapped: 0 }
  for (const id of task.competency_questions ?? []) {
    readiness.total += 1
    readiness[status.get(id) ?? 'unmapped'] += 1
  }
  return readiness
}

/**
 * The ids of the Competency Questions no Consumer's Task needs, in the Use Case's order:
 * every question of a Use Case without Consumers. Structural answerability counts them
 * as `questions_serving_no_task`.
 */
export function questionsServingNoTask(useCase: UseCase): Set<string> {
  const needed = new Set(
    (useCase.consumers ?? []).flatMap((c) => (c.tasks ?? []).flatMap((t) => t.competency_questions ?? [])),
  )
  return new Set(useCase.competency_questions.map((q) => q.id).filter((id) => !needed.has(id)))
}
