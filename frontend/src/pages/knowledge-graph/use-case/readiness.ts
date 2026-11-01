import type { Consumer, Task, UseCase } from '@/api/use-cases'
import type { StatusTone } from '@/components/status-tones'
import type { Answerability } from './answerability'

/** How many of the Competency Questions a Task needs an Ontology Version can answer. */
export interface TaskReadiness {
  /** The questions the Task needs. */
  total: number
  answerable: number
  /** Mapped onto the Ontology, but Concepts or paths are missing. */
  unanswerable: number
  /** Nothing maps them onto the Ontology, so stetiq can't check them (the UI's "Can't check"). */
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

/** A Task is ready when every question it needs is answerable, so one that needs none is. */
export function isTaskReady(readiness: TaskReadiness): boolean {
  return readiness.answerable === readiness.total
}

/**
 * A Task's readiness in words, for its icon: "Ready", or "Not ready" and why ("Not ready:
 * 1 unanswerable, 1 can't check").
 */
export function taskReadinessText(readiness: TaskReadiness): string {
  if (isTaskReady(readiness)) return 'Ready'
  const why = [
    readiness.unanswerable > 0 && `${readiness.unanswerable} unanswerable`,
    readiness.unmapped > 0 && `${readiness.unmapped} can't check`,
  ].filter(Boolean)
  return `Not ready: ${why.join(', ')}`
}

/** How many of a Consumer's Tasks the latest Ontology Version is ready for. */
export type ConsumerReadiness =
  | { state: 'no-tasks' }
  /** No Ontology Version, or it has not been judged against the Use Case Version. */
  | { state: 'not-checked' }
  | { state: 'checked'; ready: number; tasks: number }

/** `consumer`'s readiness from a stored structural answerability result, if one was judged. */
export function consumerReadiness(consumer: Consumer, answerability: Answerability | undefined): ConsumerReadiness {
  const tasks = consumer.tasks ?? []
  if (tasks.length === 0) return { state: 'no-tasks' }
  if (!answerability) return { state: 'not-checked' }
  const ready = tasks.filter((task) => isTaskReady(taskReadiness(task, answerability))).length
  return { state: 'checked', ready, tasks: tasks.length }
}

/**
 * A Consumer tile's readiness line: "1 of 2 Tasks ready", in the success tone only when all
 * are; neutral when not checked or without Tasks, so missing information never reads as a pass.
 */
export function consumerReadinessLine(readiness: ConsumerReadiness): { tone: StatusTone; label: string } {
  switch (readiness.state) {
    case 'no-tasks':
      return { tone: 'neutral', label: 'No Tasks' }
    case 'not-checked':
      return { tone: 'neutral', label: 'Not checked yet' }
    case 'checked':
      return {
        tone: readiness.ready === readiness.tasks ? 'success' : 'failure',
        label: `${readiness.ready} of ${readiness.tasks} Tasks ready`,
      }
  }
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

/** The Tasks of `useCase` that need the question `id`, each with its Consumer, in Consumer order. */
export function neededBy(useCase: UseCase, id: string): { consumer: Consumer; task: Task }[] {
  return (useCase.consumers ?? []).flatMap((consumer) =>
    (consumer.tasks ?? [])
      .filter((task) => task.competency_questions?.includes(id))
      .map((task) => ({ consumer, task })),
  )
}
