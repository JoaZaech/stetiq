import { useId, type ReactNode } from 'react'
import type { CompetencyQuestion, Consumer, Task, UseCase } from '@/api/use-cases'
import { Badge } from '@/components/ui/badge'

interface ConsumerCardsProps {
  useCase: UseCase
  /** Edit controls for a Consumer, shown in its card's header. */
  consumerActions?: (consumer: Consumer) => ReactNode
  /** Edit controls for a Task, shown beside it. */
  taskActions?: (task: Task, consumer: Consumer) => ReactNode
}

/**
 * A Use Case Version's Consumers, one card each, listing its Tasks and the Competency
 * Questions each Task needs, with the edit controls the page passes in.
 */
export function ConsumerCards({ useCase, consumerActions, taskActions }: ConsumerCardsProps) {
  const consumers = useCase.consumers ?? []
  if (consumers.length === 0) {
    return (
      <p className="rounded-lg border border-dashed p-4 text-sm text-muted-foreground">
        No Consumers are declared in this Use Case Version.
      </p>
    )
  }
  const questions = new Map(useCase.competency_questions.map((q) => [q.id, q]))
  return (
    <div className="grid gap-4 md:grid-cols-2">
      {consumers.map((consumer) => (
        <ConsumerCard
          key={consumer.id}
          consumer={consumer}
          questions={questions}
          actions={consumerActions?.(consumer)}
          taskActions={taskActions && ((task) => taskActions(task, consumer))}
        />
      ))}
    </div>
  )
}

interface ConsumerCardProps {
  consumer: Consumer
  questions: Map<string, CompetencyQuestion>
  actions?: ReactNode
  taskActions?: (task: Task) => ReactNode
}

function ConsumerCard({ consumer, questions, actions, taskActions }: ConsumerCardProps) {
  const titleId = useId()
  const tasksId = useId()
  const tasks = consumer.tasks ?? []
  return (
    <article
      aria-labelledby={titleId}
      className="min-w-0 space-y-3 rounded-xl bg-card p-4 text-sm text-card-foreground ring-1 ring-foreground/10"
    >
      <header className="space-y-1">
        <div className="flex flex-wrap items-center gap-2">
          <h4 id={titleId} className="font-semibold">
            {consumer.name}
          </h4>
          {consumer.kind && <Badge variant="secondary">{consumer.kind}</Badge>}
          <code className="font-mono text-xs text-muted-foreground">{consumer.id}</code>
          {actions && <div className="ml-auto flex items-center gap-1">{actions}</div>}
        </div>
        {consumer.contact && (
          <p className="text-xs text-muted-foreground">Contact: {consumer.contact}</p>
        )}
        {consumer.description && <p className="whitespace-pre-wrap">{consumer.description}</p>}
      </header>
      <section className="space-y-2">
        <h5 id={tasksId} className="text-xs font-medium text-muted-foreground">
          Tasks
        </h5>
        {tasks.length === 0 ? (
          <p className="text-muted-foreground">No Tasks</p>
        ) : (
          <ul aria-labelledby={tasksId} className="space-y-3">
            {tasks.map((task) => (
              <TaskItem key={task.id} task={task} questions={questions} actions={taskActions?.(task)} />
            ))}
          </ul>
        )}
      </section>
    </article>
  )
}

interface TaskItemProps {
  task: Task
  questions: Map<string, CompetencyQuestion>
  actions?: ReactNode
}

function TaskItem({ task, questions, actions }: TaskItemProps) {
  const needs = task.competency_questions ?? []
  return (
    <li className="space-y-1 border-l-2 pl-3">
      <div className="flex items-start gap-2">
        <p className="min-w-0 flex-1">
          {task.description}{' '}
          <code className="font-mono text-xs text-muted-foreground">{task.id}</code>
        </p>
        {actions && <div className="flex shrink-0 items-center gap-1">{actions}</div>}
      </div>
      {needs.length === 0 ? (
        <p className="text-xs text-muted-foreground">Needs no Competency Question</p>
      ) : (
        <ul aria-label={`Competency Questions ${task.id} needs`} className="space-y-0.5 text-xs">
          {needs.map((id) => (
            <li key={id}>
              <code className="font-mono">{id}</code>{' '}
              <span className="text-muted-foreground">{questions.get(id)?.question}</span>
            </li>
          ))}
        </ul>
      )}
    </li>
  )
}
