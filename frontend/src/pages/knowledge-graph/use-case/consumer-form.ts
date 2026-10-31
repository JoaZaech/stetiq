import type { Consumer, Task, UseCase } from '@/api/use-cases'

/** The Consumer form's fields, as typed (all text; blank optional fields = none). */
export interface ConsumerDraft {
  id: string
  name: string
  kind: string
  contact: string
  description: string
}

export type ConsumerDraftField = keyof ConsumerDraft
export type ConsumerDraftErrors = Partial<Record<ConsumerDraftField, string>>

export const EMPTY_CONSUMER_DRAFT: ConsumerDraft = { id: '', name: '', kind: '', contact: '', description: '' }

/** What already holds `id` in the Use Case, other than `own` (the id being edited). */
function holderOf(useCase: UseCase, id: string, own: string | undefined): string | undefined {
  if (id === own) return undefined
  if (useCase.competency_questions.some((q) => q.id === id)) return `The Competency Question ${id}`
  for (const consumer of useCase.consumers ?? []) {
    if (consumer.id === id) return `The Consumer ${id}`
    if ((consumer.tasks ?? []).some((t) => t.id === id)) return `The Task ${id}`
  }
  return undefined
}

function checkId(id: string, useCase: UseCase, own: string | undefined): string | undefined {
  if (!id) return 'Needs an id.'
  const holder = holderOf(useCase, id, own)
  return holder && `${holder} already has this id.`
}

/**
 * The Consumer form's errors, per field: a missing id or name, or an id that another
 * Consumer, a Task or a Competency Question of `useCase` already has. `own` is the id of
 * the Consumer being edited. Empty when the draft can be saved.
 */
export function validateConsumerDraft(
  draft: ConsumerDraft,
  useCase: UseCase,
  own?: string,
): ConsumerDraftErrors {
  const errors: ConsumerDraftErrors = {}
  const id = checkId(draft.id.trim(), useCase, own)
  if (id) errors.id = id
  if (!draft.name.trim()) errors.name = 'Needs a name.'
  return errors
}

/** The form, filled in from an existing Consumer. */
export function consumerDraftOf(consumer: Consumer): ConsumerDraft {
  return {
    id: consumer.id,
    name: consumer.name,
    kind: consumer.kind ?? '',
    contact: consumer.contact ?? '',
    description: consumer.description ?? '',
  }
}

const byId = <T extends { id: string }>(a: T, b: T) => a.id.localeCompare(b.id)

/** `useCase` with `consumers`, leaving the key out when there are none, as the wire does. */
function withConsumers(useCase: UseCase, consumers: Consumer[]): UseCase {
  const rest = { ...useCase }
  delete rest.consumers
  return consumers.length ? { ...rest, consumers: [...consumers].sort(byId) } : rest
}

/**
 * `useCase` with the Consumer `draft` describes added, or replacing the one with its id
 * (whose Tasks it keeps); unset fields are omitted, as the wire does.
 */
export function withConsumer(useCase: UseCase, draft: ConsumerDraft): UseCase {
  const id = draft.id.trim()
  const existing = useCase.consumers?.find((c) => c.id === id)
  const consumer: Consumer = { id, name: draft.name.trim() }
  for (const field of ['kind', 'contact', 'description'] as const) {
    const value = draft[field].trim()
    if (value) consumer[field] = value
  }
  if (existing?.tasks?.length) consumer.tasks = existing.tasks
  const others = (useCase.consumers ?? []).filter((c) => c.id !== id)
  return withConsumers(useCase, [...others, consumer])
}

/** `useCase` without the Consumer `id` and its Tasks; the Competency Questions stay. */
export function withoutConsumer(useCase: UseCase, id: string): UseCase {
  return withConsumers(useCase, (useCase.consumers ?? []).filter((c) => c.id !== id))
}

/** The Task form's fields: text as typed, and the ids of the questions it needs. */
export interface TaskDraft {
  id: string
  description: string
  competency_questions: string[]
}

export type TaskDraftField = keyof TaskDraft
export type TaskDraftErrors = Partial<Record<TaskDraftField, string>>

export const EMPTY_TASK_DRAFT: TaskDraft = { id: '', description: '', competency_questions: [] }

/** The form, filled in from an existing Task. */
export function taskDraftOf(task: Task): TaskDraft {
  return { id: task.id, description: task.description, competency_questions: task.competency_questions ?? [] }
}

/**
 * The Task form's errors, per field: a missing id or description, or an id that another
 * Task, a Consumer or a Competency Question of `useCase` already has. `own` is the id of
 * the Task being edited. Empty when the draft can be saved.
 */
export function validateTaskDraft(draft: TaskDraft, useCase: UseCase, own?: string): TaskDraftErrors {
  const errors: TaskDraftErrors = {}
  const id = checkId(draft.id.trim(), useCase, own)
  if (id) errors.id = id
  if (!draft.description.trim()) errors.description = 'Needs a description.'
  return errors
}

/** `consumer` with `tasks`, leaving the key out when there are none, as the wire does. */
function withTasks(consumer: Consumer, tasks: Task[]): Consumer {
  const rest = { ...consumer }
  delete rest.tasks
  return tasks.length ? { ...rest, tasks: [...tasks].sort(byId) } : rest
}

/** `useCase` with each Consumer passed through `edit`. */
function mapConsumers(useCase: UseCase, edit: (consumer: Consumer) => Consumer): UseCase {
  return withConsumers(useCase, (useCase.consumers ?? []).map(edit))
}

/** `useCase` with the Task `draft` describes added under `consumerId`, or replacing the one with its id. */
export function withTask(useCase: UseCase, consumerId: string, draft: TaskDraft): UseCase {
  const task: Task = { id: draft.id.trim(), description: draft.description.trim() }
  if (draft.competency_questions.length) task.competency_questions = [...draft.competency_questions].sort()
  return mapConsumers(useCase, (consumer) => {
    if (consumer.id !== consumerId) return consumer
    const others = (consumer.tasks ?? []).filter((t) => t.id !== task.id)
    return withTasks(consumer, [...others, task])
  })
}

/** `useCase` with every Task passed through `edit`. */
export function mapTasks(useCase: UseCase, edit: (task: Task) => Task): UseCase {
  return mapConsumers(useCase, (consumer) =>
    consumer.tasks ? withTasks(consumer, consumer.tasks.map(edit)) : consumer,
  )
}

/** `useCase` without the Task `id`. */
export function withoutTask(useCase: UseCase, id: string): UseCase {
  return mapConsumers(useCase, (consumer) =>
    consumer.tasks?.some((t) => t.id === id)
      ? withTasks(consumer, consumer.tasks.filter((t) => t.id !== id))
      : consumer,
  )
}
