import { useCallback, useId, useState, type ReactNode } from 'react'
import { Plus } from 'lucide-react'
import { useUseCaseVersions, type SavedUseCase, type UseCase, type UseCaseVersion } from '@/api/use-cases'
import { knowledgeGraphSection } from '@/app/knowledge-graph-sections'
import { ErrorAlert } from '@/components/ErrorAlert'
import { NeedsEditAccess } from '@/components/NeedsEditAccess'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { formatDateTime } from '@/lib/format'
import { useSheetParam } from '@/lib/sheet-param'
import { KnowledgeGraphSectionPage } from '../KnowledgeGraphSectionPage'
import { useKnowledgeGraphName } from '../params'
import { CompetencyQuestionDialog } from './CompetencyQuestionDialog'
import { CompetencyQuestionSheet } from './CompetencyQuestionSheet'
import { CompetencyQuestionsList } from './CompetencyQuestionsList'
import { ConsumerDialog } from './ConsumerDialog'
import { ConsumerSheet } from './ConsumerSheet'
import { ConsumerTiles } from './ConsumerTiles'
import { DraftWithAiPlanned } from './planned'
import { savedMessage } from './saved-message'
import { UseCaseVersionsTable } from './UseCaseVersionsTable'

const SECTION = knowledgeGraphSection('use-case')

/** What an editor adds the first Competency Question to. */
const NO_USE_CASE: UseCase = { competency_questions: [] }

/** The side sheets this page opens (`?sheet=`). */
const SHEET_KINDS = ['question', 'consumer'] as const

/**
 * `/kg/:name/use-case`: the latest Use Case Version (description, Competency Questions,
 * and its Consumers with their Tasks), then every Use Case Version, to compare.
 *
 * Editors add, edit and remove Competency Questions, Consumers and their Tasks here; each
 * save sends the complete edited Use Case and registers a new Use Case Version. A
 * Competency Question and a Consumer each open in a side sheet, kept in the URL
 * (`?sheet=question:<id>`, `?sheet=consumer:<id>`). A question opened from a Consumer's
 * sheet replaces its content, and `?sheet-back=consumer:<id>` keeps where its Back returns.
 */
export function UseCasePage() {
  const name = useKnowledgeGraphName()
  const versions = useUseCaseVersions(name)
  const [saved, setSaved] = useState<SavedUseCase>()
  const latest = versions.data?.at(-1)
  const { sheet, back, openSheet, closeSheet, goBack } = useSheetParam(SHEET_KINDS)
  const openQuestion = useCallback((id: string) => openSheet({ kind: 'question', id }), [openSheet])
  const openConsumer = useCallback((id: string) => openSheet({ kind: 'consumer', id }), [openSheet])
  const sheetQuestion =
    sheet?.kind === 'question' ? latest?.use_case.competency_questions.find((q) => q.id === sheet.id) : undefined
  // The Consumer sheet is open on its Consumer, or on a question opened from it.
  const consumerId = sheet?.kind === 'consumer' ? sheet.id : back?.kind === 'consumer' ? back.id : undefined
  const sheetConsumer = latest?.use_case.consumers?.find((c) => c.id === consumerId)

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
              <LatestVersion name={name} version={latest} onOpenQuestion={openQuestion} />
              <Consumers name={name} version={latest} onSaved={setSaved} onOpenConsumer={openConsumer} />
              <Panel title="Use Case Versions">
                <UseCaseVersionsTable name={name} versions={versions.data} />
              </Panel>
              <CompetencyQuestionSheet
                knowledgeGraph={name}
                useCaseVersion={latest}
                question={sheetConsumer ? undefined : sheetQuestion}
                onClose={closeSheet}
                onSaved={setSaved}
                onRemoved={closeSheet}
              />
              <ConsumerSheet
                knowledgeGraph={name}
                useCaseVersion={latest}
                consumer={sheetConsumer}
                question={sheetQuestion}
                onOpenQuestion={(id) =>
                  sheetConsumer && openSheet({ kind: 'question', id }, { kind: 'consumer', id: sheetConsumer.id })
                }
                onBack={goBack}
                onClose={closeSheet}
                onSaved={setSaved}
                onRemoved={closeSheet}
              />
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
  /** Opens the Competency Question's sheet. */
  onOpenQuestion: (id: string) => void
}

function LatestVersion({ name, version, onOpenQuestion }: LatestVersionProps) {
  const useCase = version.use_case
  return (
    <Panel title={`Use Case Version ${version.number}`}>
      <p className="text-xs text-muted-foreground">
        Latest, created {formatDateTime(version.created_at)}
      </p>
      <p className="text-sm">
        {useCase.description ?? <span className="text-muted-foreground">No description</span>}
      </p>
      <CompetencyQuestionsList knowledgeGraph={name} version={version} onOpen={(q) => onOpenQuestion(q.id)} />
    </Panel>
  )
}

interface ConsumersProps {
  name: string
  version: UseCaseVersion
  onSaved: (saved: SavedUseCase) => void
  /** Opens the Consumer's sheet, where it and its Tasks are edited. */
  onOpenConsumer: (id: string) => void
}

/** The latest Use Case Version's Consumers as tiles; each opens its sheet. */
function Consumers({ name, version, onSaved, onOpenConsumer }: ConsumersProps) {
  return (
    <Panel
      title="Consumers"
      actions={
        <div className="flex flex-wrap items-center justify-end gap-2">
          <DraftWithAiPlanned />
          <NeedsEditAccess knowledgeGraph={name}>
            {(disabled) => (
              <ConsumerDialog
                knowledgeGraph={name}
                useCase={version.use_case}
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
        </div>
      }
    >
      <ConsumerTiles knowledgeGraph={name} version={version} onOpen={(c) => onOpenConsumer(c.id)} />
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
