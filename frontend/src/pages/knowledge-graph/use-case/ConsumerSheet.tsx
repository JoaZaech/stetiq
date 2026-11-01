import { useId, useState, type ReactNode } from 'react'
import { ArrowLeft, ChevronRight, Pencil, Plus, Trash2 } from 'lucide-react'
import type { CompetencyQuestion, Consumer, SavedUseCase, Task, UseCaseVersion } from '@/api/use-cases'
import { NeedsEditAccess } from '@/components/NeedsEditAccess'
import { StatusIcon } from '@/components/StatusLabel'
import { Button } from '@/components/ui/button'
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from '@/components/ui/sheet'
import { cn } from '@/lib/utils'
import { AnswerabilityLabel } from './AnswerabilityLabel'
import { CompetencyQuestionSheetContent } from './CompetencyQuestionSheet'
import { ConfirmRemoveDialog, TaskList } from './ConfirmRemoveDialog'
import { ConsumerDialog } from './ConsumerDialog'
import { ConsumerGateSection } from './ConsumerGateSection'
import { withoutConsumer, withoutTask } from './consumer-form'
import { CONSUMER_KIND_ICONS, consumerKindIcon } from './consumer-kind'
import { useLatestAnswerability, type LatestAnswerability } from './latest-answerability'
import { isTaskReady, taskReadiness, taskReadinessText } from './readiness'
import { focusSheetItself } from './sheet-focus'
import { SheetSection } from './sheet-section'
import { TaskDialog } from './TaskDialog'

interface ConsumerSheetProps {
  knowledgeGraph: string
  /** The latest Use Case Version: every edit saves it edited as a new one. */
  useCaseVersion: UseCaseVersion
  /** The Consumer shown; the sheet is open while it is set. */
  consumer: Consumer | undefined
  /** A question opened from the sheet, shown in place of the Consumer, with Back. */
  question: CompetencyQuestion | undefined
  onOpenQuestion: (id: string) => void
  /** Returns from `question` to the Consumer. */
  onBack: () => void
  onClose: () => void
  onSaved: (saved: SavedUseCase) => void
  /** Called once removing the Consumer has saved (e.g. to close the sheet). */
  onRemoved: () => void
}

/**
 * The Consumer side sheet, open while `consumer` is set. A question clicked in it replaces
 * its content with the question's sheet content and a **Back** link: sheets never stack.
 */
export function ConsumerSheet({
  knowledgeGraph,
  useCaseVersion,
  consumer,
  question,
  onOpenQuestion,
  onBack,
  onClose,
  onSaved,
  onRemoved,
}: ConsumerSheetProps) {
  return (
    <Sheet open={consumer !== undefined} onOpenChange={(open) => !open && onClose()}>
      <SheetContent className="overflow-y-auto sm:max-w-md" onOpenAutoFocus={focusSheetItself}>
        {consumer &&
          (question ? (
            <>
              <div className="-mb-4 px-4 pt-3">
                <Button variant="link" size="sm" className="px-0" onClick={onBack} autoFocus>
                  <ArrowLeft />
                  Back
                </Button>
              </div>
              <CompetencyQuestionSheetContent
                knowledgeGraph={knowledgeGraph}
                useCaseVersion={useCaseVersion}
                question={question}
                onSaved={onSaved}
                onRemoved={onBack}
              />
            </>
          ) : (
            <ConsumerSheetContent
              knowledgeGraph={knowledgeGraph}
              useCaseVersion={useCaseVersion}
              consumer={consumer}
              onOpenQuestion={onOpenQuestion}
              onSaved={onSaved}
              onRemoved={onRemoved}
            />
          ))}
      </SheetContent>
    </Sheet>
  )
}

type ConsumerSheetContentProps = Pick<
  ConsumerSheetProps,
  'knowledgeGraph' | 'useCaseVersion' | 'onOpenQuestion' | 'onSaved' | 'onRemoved'
> & { consumer: Consumer }

/**
 * What the Consumer sheet shows: its kind, name, id, contact and description, Edit and
 * Remove in the header, then its Tasks (each with its readiness, expanding to the questions
 * it needs) with their edit controls, then its Consumer Gate.
 */
function ConsumerSheetContent({
  knowledgeGraph,
  useCaseVersion,
  consumer,
  onOpenQuestion,
  onSaved,
  onRemoved,
}: ConsumerSheetContentProps) {
  const useCase = useCaseVersion.use_case
  const latest = useLatestAnswerability(knowledgeGraph, useCaseVersion.number)
  const tasks = consumer.tasks ?? []
  const Icon = CONSUMER_KIND_ICONS[consumerKindIcon(consumer.kind)]
  return (
    <>
      <SheetHeader className="gap-2 pr-12">
        <SheetDescription className="flex items-center gap-1.5">
          <Icon aria-hidden className="size-4" />
          Consumer
        </SheetDescription>
        <SheetTitle>{consumer.name}</SheetTitle>
        <div className="flex gap-2 pt-1">
          <NeedsEditAccess knowledgeGraph={knowledgeGraph}>
            {(disabled) => (
              <ConsumerDialog
                knowledgeGraph={knowledgeGraph}
                useCase={useCase}
                consumer={consumer}
                onSaved={onSaved}
                trigger={
                  <Button variant="outline" size="sm" disabled={disabled}>
                    <Pencil />
                    Edit
                  </Button>
                }
              />
            )}
          </NeedsEditAccess>
          <NeedsEditAccess knowledgeGraph={knowledgeGraph}>
            {(disabled) => (
              <ConfirmRemoveDialog
                knowledgeGraph={knowledgeGraph}
                title={`Remove ${consumer.name}?`}
                description={
                  tasks.length
                    ? 'It will not be in the new Use Case Version, and neither will its Tasks. The Competency Questions stay.'
                    : 'It will not be in the new Use Case Version. The Competency Questions stay.'
                }
                next={() => withoutConsumer(useCase, consumer.id)}
                onSaved={(saved) => {
                  onSaved(saved)
                  onRemoved()
                }}
                trigger={
                  <Button variant="outline" size="sm" disabled={disabled}>
                    <Trash2 />
                    Remove
                  </Button>
                }
              >
                {tasks.length ? <TaskList label="Tasks removed with it" tasks={tasks} /> : null}
              </ConfirmRemoveDialog>
            )}
          </NeedsEditAccess>
        </div>
      </SheetHeader>
      <div className="space-y-6 px-4 pb-4">
        {consumer.description && <p className="whitespace-pre-wrap">{consumer.description}</p>}
        <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-2">
          <dt className="text-muted-foreground">Kind</dt>
          <dd>{consumer.kind ?? <span className="text-muted-foreground">None</span>}</dd>
          <dt className="text-muted-foreground">Id</dt>
          <dd>
            <code className="font-mono text-xs">{consumer.id}</code>
          </dd>
          <dt className="text-muted-foreground">Contact</dt>
          <dd>{consumer.contact ?? <span className="text-muted-foreground">None</span>}</dd>
        </dl>
        <SheetSection
          title="Tasks"
          actions={
            <NeedsEditAccess knowledgeGraph={knowledgeGraph}>
              {(disabled) => (
                <TaskDialog
                  knowledgeGraph={knowledgeGraph}
                  useCase={useCase}
                  consumer={consumer}
                  onSaved={onSaved}
                  trigger={
                    <Button variant="outline" size="sm" disabled={disabled}>
                      <Plus />
                      Add Task
                    </Button>
                  }
                />
              )}
            </NeedsEditAccess>
          }
        >
          {tasks.length === 0 ? (
            <p className="text-muted-foreground">No Tasks</p>
          ) : (
            <ul aria-label="Tasks" className="divide-y rounded-lg border">
              {tasks.map((task) => (
                <TaskItem
                  key={task.id}
                  task={task}
                  questions={useCase.competency_questions}
                  latest={latest}
                  onOpenQuestion={onOpenQuestion}
                  actions={
                    <TaskActions
                      knowledgeGraph={knowledgeGraph}
                      useCaseVersion={useCaseVersion}
                      consumer={consumer}
                      task={task}
                      onSaved={onSaved}
                    />
                  }
                />
              ))}
            </ul>
          )}
        </SheetSection>
        <ConsumerGateSection knowledgeGraph={knowledgeGraph} consumer={consumer} />
      </div>
    </>
  )
}

interface TaskItemProps {
  task: Task
  questions: CompetencyQuestion[]
  latest: LatestAnswerability
  onOpenQuestion: (id: string) => void
  actions: ReactNode
}

/** A Task with its readiness icon; it expands to the questions it needs, each with its status. */
function TaskItem({ task, questions, latest, onOpenQuestion, actions }: TaskItemProps) {
  const [expanded, setExpanded] = useState(false)
  const listId = useId()
  const needs = task.competency_questions ?? []
  const status = latest.state === 'judged' ? new Map(latest.answerability.rows.map((r) => [r.id, r.status])) : null
  return (
    <li>
      <div className="flex items-start gap-2 px-3 py-2">
        <button
          type="button"
          aria-expanded={expanded}
          aria-controls={listId}
          onClick={() => setExpanded((e) => !e)}
          className="flex min-w-0 flex-1 items-start gap-2 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          <ChevronRight
            aria-hidden
            className={cn('mt-0.5 size-4 shrink-0 text-muted-foreground transition-transform', expanded && 'rotate-90')}
          />
          <span className="mt-0.5">
            <TaskStatus task={task} latest={latest} />
          </span>
          <span className="min-w-0 flex-1">
            {task.description}{' '}
            <code className="font-mono text-xs whitespace-nowrap text-muted-foreground">{task.id}</code>
          </span>
        </button>
        <div className="flex shrink-0 items-center gap-1">{actions}</div>
      </div>
      <div id={listId} hidden={!expanded} className="pb-2 pl-9 pr-3">
        {needs.length === 0 ? (
          <p className="text-xs text-muted-foreground">Needs no Competency Question</p>
        ) : (
          <ul aria-label={`Competency Questions ${task.id} needs`} className="space-y-0.5">
            {needs.map((id) => {
              const answerability = status?.get(id)
              return (
                <li key={id}>
                  <button
                    type="button"
                    onClick={() => onOpenQuestion(id)}
                    className="flex w-full flex-wrap items-center gap-x-3 gap-y-0.5 rounded-md px-2 py-1 text-left hover:bg-muted/50 focus-visible:bg-muted/50 focus-visible:outline-none"
                  >
                    <span className="min-w-0 flex-1">{questions.find((q) => q.id === id)?.question ?? id}</span>
                    {answerability && <AnswerabilityLabel status={answerability} />}
                  </button>
                </li>
              )
            })}
          </ul>
        )}
      </div>
    </li>
  )
}

/** Whether the latest Ontology Version answers every question the Task needs, as an icon. */
function TaskStatus({ task, latest }: { task: Task; latest: LatestAnswerability }) {
  switch (latest.state) {
    case 'pending':
    case 'error':
      return null
    case 'no-ontology':
    case 'not-judged':
      return <StatusIcon tone="neutral" label="Not checked yet" />
    case 'judged': {
      const readiness = taskReadiness(task, latest.answerability)
      return <StatusIcon tone={isTaskReady(readiness) ? 'success' : 'failure'} label={taskReadinessText(readiness)} />
    }
  }
}

interface TaskActionsProps {
  knowledgeGraph: string
  useCaseVersion: UseCaseVersion
  consumer: Consumer
  task: Task
  onSaved: (saved: SavedUseCase) => void
}

function TaskActions({ knowledgeGraph, useCaseVersion, consumer, task, onSaved }: TaskActionsProps) {
  const useCase = useCaseVersion.use_case
  return (
    <>
      <NeedsEditAccess knowledgeGraph={knowledgeGraph}>
        {(disabled) => (
          <TaskDialog
            knowledgeGraph={knowledgeGraph}
            useCase={useCase}
            consumer={consumer}
            task={task}
            onSaved={onSaved}
            trigger={
              <Button variant="ghost" size="icon-xs" disabled={disabled} aria-label={`Edit Task ${task.id}`}>
                <Pencil />
              </Button>
            }
          />
        )}
      </NeedsEditAccess>
      <NeedsEditAccess knowledgeGraph={knowledgeGraph}>
        {(disabled) => (
          <ConfirmRemoveDialog
            knowledgeGraph={knowledgeGraph}
            title={`Remove ${task.id}?`}
            description={`“${task.description}” will not be in the new Use Case Version. The Competency Questions it needs stay.`}
            next={() => withoutTask(useCase, task.id)}
            onSaved={onSaved}
            trigger={
              <Button variant="ghost" size="icon-xs" disabled={disabled} aria-label={`Remove Task ${task.id}`}>
                <Trash2 />
              </Button>
            }
          />
        )}
      </NeedsEditAccess>
    </>
  )
}
