import { useId } from 'react'
import type { CompetencyQuestion, Consumer, Task, UseCase } from '@/api/use-cases'
import { Badge } from '@/components/ui/badge'

/**
 * A Use Case Version's Consumers, one card each, listing its Tasks and the Competency
 * Questions each Task needs. Read-only.
 */
export function ConsumerCards({ useCase }: { useCase: UseCase }) {
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
        <ConsumerCard key={consumer.id} consumer={consumer} questions={questions} />
      ))}
    </div>
  )
}

interface ConsumerCardProps {
  consumer: Consumer
  questions: Map<string, CompetencyQuestion>
}

function ConsumerCard({ consumer, questions }: ConsumerCardProps) {
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
              <TaskItem key={task.id} task={task} questions={questions} />
            ))}
          </ul>
        )}
      </section>
    </article>
  )
}

function TaskItem({ task, questions }: { task: Task; questions: Map<string, CompetencyQuestion> }) {
  const needs = task.competency_questions ?? []
  return (
    <li className="space-y-1 border-l-2 pl-3">
      <p>
        {task.description}{' '}
        <code className="font-mono text-xs text-muted-foreground">{task.id}</code>
      </p>
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
