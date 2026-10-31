import { useCallback, useId, useState, type ReactNode } from 'react'
import { Pencil, Plus, Trash2 } from 'lucide-react'
import {
  useUseCaseVersions,
  type CompetencyQuestion,
  type Consumer,
  type SavedUseCase,
  type Task,
  type UseCase,
  type UseCaseVersion,
} from '@/api/use-cases'
import { knowledgeGraphSection } from '@/app/knowledge-graph-sections'
import { ErrorAlert } from '@/components/ErrorAlert'
import { NeedsEditAccess } from '@/components/NeedsEditAccess'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { formatDateTime } from '@/lib/format'
import { KnowledgeGraphSectionPage } from '../KnowledgeGraphSectionPage'
import { useKnowledgeGraphName } from '../params'
import { CompetencyQuestionDialog } from './CompetencyQuestionDialog'
import { CompetencyQuestionsTable } from './CompetencyQuestionsTable'
import { ConfirmRemoveDialog, TaskList } from './ConfirmRemoveDialog'
import { ConsumerCards } from './ConsumerCards'
import { ConsumerDialog } from './ConsumerDialog'
import { withoutConsumer, withoutTask } from './consumer-form'
import { RemoveCompetencyQuestionDialog } from './RemoveCompetencyQuestionDialog'
import { savedMessage } from './saved-message'
import { StructuralAnswerability } from './StructuralAnswerability'
import { TaskDialog } from './TaskDialog'
import { UseCaseVersionsTable } from './UseCaseVersionsTable'

const SECTION = knowledgeGraphSection('use-case')

/** What an editor adds the first Competency Question to. */
const NO_USE_CASE: UseCase = { competency_questions: [] }

/**
 * `/kg/:name/use-case`: the latest Use Case Version (description, Competency Questions,
 * and its Consumers with their Tasks), then every Use Case Version, to compare.
 *
 * Editors add, edit and remove Competency Questions, Consumers and their Tasks here; each
 * save sends the complete edited Use Case and registers a new Use Case Version.
 */
export function UseCasePage() {
  const name = useKnowledgeGraphName()
  const versions = useUseCaseVersions(name)
  const [saved, setSaved] = useState<SavedUseCase>()
  const latest = versions.data?.at(-1)

  return (
    <KnowledgeGraphSectionPage
      section={SECTION}
      actions={
        versions.isSuccess && (
          <NeedsEditAccess knowledgeGraph={name}>
            {(disabled) => (
              <CompetencyQuestionDialog
                knowledgeGraph={name}
                useCase={latest?.use_case ?? NO_USE_CASE}
                onSaved={setSaved}
                trigger={
                  <Button size="sm" disabled={disabled}>
                    <Plus />
                    Add Competency Question
                  </Button>
                }
              />
            )}
          </NeedsEditAccess>
        )
      }
    >
      {versions.isError ? (
        <ErrorAlert error={versions.error} />
      ) : versions.isPending ? (
        <Skeleton className="h-32 w-full" />
      ) : (
        <div className="space-y-8">
          {saved && <SavedStatus saved={saved} />}
          {latest ? (
            <>
              <LatestVersion name={name} version={latest} onSaved={setSaved} />
              <Consumers name={name} useCase={latest.use_case} onSaved={setSaved} />
              <StructuralAnswerability knowledgeGraph={name} useCaseVersion={latest.number} />
              <Panel title="Use Case Versions">
                <UseCaseVersionsTable name={name} versions={versions.data} />
              </Panel>
            </>
          ) : (
            <p className="rounded-lg border border-dashed p-6 text-sm text-muted-foreground">
              No Use Case has been registered yet. Add a Competency Question, or register one with{' '}
              <code className="font-mono text-xs">client.register_use_case("{name}", …)</code>.
            </p>
          )}
        </div>
      )}
    </KnowledgeGraphSectionPage>
  )
}

function SavedStatus({ saved }: { saved: SavedUseCase }) {
  return (
    <p role="status" className="rounded-lg border bg-muted/40 px-3 py-2 text-sm">
      {savedMessage(saved)}
    </p>
  )
}

interface LatestVersionProps {
  name: string
  version: UseCaseVersion
  onSaved: (saved: SavedUseCase) => void
}

function LatestVersion({ name, version, onSaved }: LatestVersionProps) {
  const useCase = version.use_case
  const rowActions = useCallback(
    (question: CompetencyQuestion) => (
      <>
        <NeedsEditAccess knowledgeGraph={name}>
          {(disabled) => (
            <CompetencyQuestionDialog
              knowledgeGraph={name}
              useCase={useCase}
              question={question}
              onSaved={onSaved}
              trigger={
                <Button variant="ghost" size="icon-sm" disabled={disabled} aria-label={`Edit ${question.id}`}>
                  <Pencil />
                </Button>
              }
            />
          )}
        </NeedsEditAccess>
        <NeedsEditAccess knowledgeGraph={name}>
          {(disabled) => (
            <RemoveCompetencyQuestionDialog
              knowledgeGraph={name}
              useCase={useCase}
              question={question}
              onSaved={onSaved}
              trigger={
                <Button variant="ghost" size="icon-sm" disabled={disabled} aria-label={`Remove ${question.id}`}>
                  <Trash2 />
                </Button>
              }
            />
          )}
        </NeedsEditAccess>
      </>
    ),
    [name, useCase, onSaved],
  )
  return (
    <Panel title={`Use Case Version ${version.number}`}>
      <p className="text-xs text-muted-foreground">
        Latest, created {formatDateTime(version.created_at)}
      </p>
      <p className="text-sm">
        {useCase.description ?? <span className="text-muted-foreground">No description</span>}
      </p>
      <CompetencyQuestionsTable questions={useCase.competency_questions} rowActions={rowActions} />
    </Panel>
  )
}

interface ConsumersProps {
  name: string
  useCase: UseCase
  onSaved: (saved: SavedUseCase) => void
}

/** The latest Use Case Version's Consumer cards, with their edit controls. */
function Consumers({ name, useCase, onSaved }: ConsumersProps) {
  const consumerActions = useCallback(
    (consumer: Consumer) => (
      <>
        <NeedsEditAccess knowledgeGraph={name}>
          {(disabled) => (
            <TaskDialog
              knowledgeGraph={name}
              useCase={useCase}
              consumer={consumer}
              onSaved={onSaved}
              trigger={
                <Button variant="ghost" size="icon-sm" disabled={disabled} aria-label={`Add Task to ${consumer.id}`}>
                  <Plus />
                </Button>
              }
            />
          )}
        </NeedsEditAccess>
        <NeedsEditAccess knowledgeGraph={name}>
          {(disabled) => (
            <ConsumerDialog
              knowledgeGraph={name}
              useCase={useCase}
              consumer={consumer}
              onSaved={onSaved}
              trigger={
                <Button variant="ghost" size="icon-sm" disabled={disabled} aria-label={`Edit Consumer ${consumer.id}`}>
                  <Pencil />
                </Button>
              }
            />
          )}
        </NeedsEditAccess>
        <NeedsEditAccess knowledgeGraph={name}>
          {(disabled) => (
            <ConfirmRemoveDialog
              knowledgeGraph={name}
              title={`Remove ${consumer.name}?`}
              description={
                consumer.tasks?.length
                  ? 'It will not be in the new Use Case Version, and neither will its Tasks. The Competency Questions stay.'
                  : 'It will not be in the new Use Case Version. The Competency Questions stay.'
              }
              next={() => withoutConsumer(useCase, consumer.id)}
              onSaved={onSaved}
              trigger={
                <Button variant="ghost" size="icon-sm" disabled={disabled} aria-label={`Remove Consumer ${consumer.id}`}>
                  <Trash2 />
                </Button>
              }
            >
              {consumer.tasks?.length ? <TaskList label="Tasks removed with it" tasks={consumer.tasks} /> : null}
            </ConfirmRemoveDialog>
          )}
        </NeedsEditAccess>
      </>
    ),
    [name, useCase, onSaved],
  )
  const taskActions = useCallback(
    (task: Task, consumer: Consumer) => (
      <>
        <NeedsEditAccess knowledgeGraph={name}>
          {(disabled) => (
            <TaskDialog
              knowledgeGraph={name}
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
        <NeedsEditAccess knowledgeGraph={name}>
          {(disabled) => (
            <ConfirmRemoveDialog
              knowledgeGraph={name}
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
    ),
    [name, useCase, onSaved],
  )
  return (
    <Panel
      title="Consumers"
      actions={
        <NeedsEditAccess knowledgeGraph={name}>
          {(disabled) => (
            <ConsumerDialog
              knowledgeGraph={name}
              useCase={useCase}
              onSaved={onSaved}
              trigger={
                <Button variant="outline" size="sm" disabled={disabled}>
                  <Plus />
                  Add Consumer
                </Button>
              }
            />
          )}
        </NeedsEditAccess>
      }
    >
      <ConsumerCards useCase={useCase} consumerActions={consumerActions} taskActions={taskActions} />
    </Panel>
  )
}

interface PanelProps {
  title: string
  /** Controls beside the title. */
  actions?: ReactNode
  children: ReactNode
}

function Panel({ title, actions, children }: PanelProps) {
  const id = useId()
  return (
    <section aria-labelledby={id} className="min-w-0 space-y-3">
      <div className="flex items-center justify-between gap-2">
        <h3 id={id} className="text-sm font-semibold">
          {title}
        </h3>
        {actions}
      </div>
      {children}
    </section>
  )
}
