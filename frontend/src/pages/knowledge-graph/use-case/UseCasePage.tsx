import { useCallback, useId, useState, type ReactNode } from 'react'
import { Pencil, Plus, Trash2 } from 'lucide-react'
import {
  useUseCaseVersions,
  type CompetencyQuestion,
  type SavedUseCase,
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
import { RemoveCompetencyQuestionDialog } from './RemoveCompetencyQuestionDialog'
import { UseCaseVersionsTable } from './UseCaseVersionsTable'

const SECTION = knowledgeGraphSection('use-case')

/** What an editor adds the first Competency Question to. */
const NO_USE_CASE: UseCase = { competency_questions: [] }

/**
 * `/kg/:name/use-case`: the latest Use Case Version (description and Competency
 * Questions), then every Use Case Version, to compare.
 *
 * Editors add, edit and remove Competency Questions here; each save sends the complete
 * edited Use Case and registers a new Use Case Version.
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
      {saved.created
        ? `Saved as Use Case Version ${saved.version.number}.`
        : `Nothing changed: this content is already Use Case Version ${saved.version.number}, so no new version was created.`}
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

function Panel({ title, children }: { title: string; children: ReactNode }) {
  const id = useId()
  return (
    <section aria-labelledby={id} className="min-w-0 space-y-3">
      <h3 id={id} className="text-sm font-semibold">
        {title}
      </h3>
      {children}
    </section>
  )
}
