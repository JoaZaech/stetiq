import { useId, type ReactNode } from 'react'
import { Pencil, Trash2 } from 'lucide-react'
import type { CompetencyQuestion, SavedUseCase, UseCaseVersion } from '@/api/use-cases'
import { ErrorAlert } from '@/components/ErrorAlert'
import { NeedsEditAccess } from '@/components/NeedsEditAccess'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from '@/components/ui/sheet'
import { Skeleton } from '@/components/ui/skeleton'
import { AnswerabilityLabel } from './AnswerabilityLabel'
import { CompetencyQuestionDialog } from './CompetencyQuestionDialog'
import { ConceptMapping, ExpectedAnswer, Query } from './fields'
import { useLatestAnswerability } from './latest-answerability'
import { neededBy } from './readiness'
import { RemoveCompetencyQuestionDialog } from './RemoveCompetencyQuestionDialog'

export interface CompetencyQuestionSheetContentProps {
  knowledgeGraph: string
  /** The Use Case Version the question belongs to: its status and Needed by are read from it. */
  useCaseVersion: UseCaseVersion
  question: CompetencyQuestion
  /** More about the question, shown after its status and missing Concepts (e.g. a run's check). */
  children?: ReactNode
  /**
   * Shows Edit and Remove in the header, which save `useCaseVersion` edited as a new Use
   * Case Version: pass it only when `useCaseVersion` is the latest.
   */
  onSaved?: (saved: SavedUseCase) => void
  /** Called once Remove has saved, since the question is gone (e.g. to close the sheet). */
  onRemoved?: () => void
}

interface CompetencyQuestionSheetProps extends Omit<CompetencyQuestionSheetContentProps, 'question'> {
  /** The question shown; the sheet is open while it is set. */
  question: CompetencyQuestion | undefined
  onClose: () => void
}

/** The Competency Question side sheet, open while `question` is set. */
export function CompetencyQuestionSheet({ question, onClose, ...props }: CompetencyQuestionSheetProps) {
  return (
    <Sheet open={question !== undefined} onOpenChange={(open) => !open && onClose()}>
      <SheetContent
        className="overflow-y-auto sm:max-w-md"
        // Focus the sheet, not Edit: for a reader, that would open its "Needs edit access" tooltip.
        onOpenAutoFocus={(event) => {
          event.preventDefault()
          ;(event.currentTarget as HTMLElement).focus()
        }}
      >
        {question && <CompetencyQuestionSheetContent question={question} {...props} />}
      </SheetContent>
    </Sheet>
  )
}

/**
 * What the Competency Question sheet shows, in order: the question and its status on the
 * latest Ontology Version, the Concepts it is missing, `children`, the Consumers' Tasks
 * that need it (Needed by), and its Author details. Render it inside a `SheetContent`;
 * the sheet of another element can show it in place of its own content.
 */
export function CompetencyQuestionSheetContent({
  knowledgeGraph,
  useCaseVersion,
  question,
  children,
  onSaved,
  onRemoved,
}: CompetencyQuestionSheetContentProps) {
  const useCase = useCaseVersion.use_case
  const needs = neededBy(useCase, question.id)
  return (
    <>
      <SheetHeader className="gap-2 pr-12">
        <SheetDescription>Competency Question</SheetDescription>
        <SheetTitle>{question.question}</SheetTitle>
        <Status knowledgeGraph={knowledgeGraph} useCaseVersion={useCaseVersion.number} questionId={question.id} />
        {onSaved && (
          <div className="flex gap-2 pt-1">
            <NeedsEditAccess knowledgeGraph={knowledgeGraph}>
              {(disabled) => (
                <CompetencyQuestionDialog
                  knowledgeGraph={knowledgeGraph}
                  useCase={useCase}
                  question={question}
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
                <RemoveCompetencyQuestionDialog
                  knowledgeGraph={knowledgeGraph}
                  useCase={useCase}
                  question={question}
                  onSaved={(saved) => {
                    onSaved(saved)
                    onRemoved?.()
                  }}
                  trigger={
                    <Button variant="outline" size="sm" disabled={disabled}>
                      <Trash2 />
                      Remove
                    </Button>
                  }
                />
              )}
            </NeedsEditAccess>
          </div>
        )}
      </SheetHeader>
      <div className="space-y-6 px-4 pb-4">
        <MissingConcepts
          knowledgeGraph={knowledgeGraph}
          useCaseVersion={useCaseVersion.number}
          questionId={question.id}
        />
        {children}
        <Section title="Needed by">
          {needs.length === 0 ? (
            <p className="text-muted-foreground">Not used by any Task</p>
          ) : (
            <ul className="space-y-1">
              {needs.map(({ consumer, task }) => (
                <li key={task.id}>
                  <span className="font-medium">{consumer.name}</span> · {task.description}
                </li>
              ))}
            </ul>
          )}
        </Section>
        <Section title="Author details">
          <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-2">
            <dt className="text-muted-foreground">Id</dt>
            <dd>
              <code className="font-mono text-xs">{question.id}</code>
            </dd>
            <dt className="text-muted-foreground">Cypher query</dt>
            <dd className="min-w-0">
              <Query value={question.query} />
            </dd>
            <dt className="text-muted-foreground">Expected answer</dt>
            <dd className="min-w-0">
              <ExpectedAnswer value={question.expected_answer} />
            </dd>
            <dt className="text-muted-foreground">Concept mapping</dt>
            <dd className="min-w-0">
              <ConceptMapping value={question.concepts} />
            </dd>
          </dl>
        </Section>
      </div>
    </>
  )
}

interface QuestionAnswerabilityProps {
  knowledgeGraph: string
  useCaseVersion: number
  questionId: string
}

/** The question's status on the latest Ontology Version, or why it has none. */
function Status({ knowledgeGraph, useCaseVersion, questionId }: QuestionAnswerabilityProps) {
  const latest = useLatestAnswerability(knowledgeGraph, useCaseVersion)
  switch (latest.state) {
    case 'error':
      return <ErrorAlert error={latest.error} />
    case 'pending':
      return <Skeleton className="h-5 w-40" />
    case 'no-ontology':
      return <p className="text-muted-foreground">No Ontology Version to check it against yet</p>
    case 'not-judged':
      return <p className="text-muted-foreground">Not judged on v{latest.ontologyVersion} yet</p>
    case 'judged': {
      const row = latest.answerability.rows.find((r) => r.id === questionId)
      if (!row) return null
      return (
        <p className="flex flex-wrap items-center gap-1.5">
          <AnswerabilityLabel status={row.status} />{' '}
          <span className="text-muted-foreground">on Ontology Version v{latest.ontologyVersion}</span>
        </p>
      )
    }
  }
}

/** The Concepts an unanswerable question needs and the latest Ontology Version lacks, as chips. */
function MissingConcepts({ knowledgeGraph, useCaseVersion, questionId }: QuestionAnswerabilityProps) {
  const latest = useLatestAnswerability(knowledgeGraph, useCaseVersion)
  const row = latest.state === 'judged' ? latest.answerability.rows.find((r) => r.id === questionId) : undefined
  if (row?.status !== 'unanswerable' || row.missing.length === 0) return null
  return (
    <Section title="Missing Concepts">
      <ul className="flex flex-wrap gap-1.5">
        {row.missing.map((concept) => (
          <li key={concept}>
            <Badge variant="outline" className="font-mono">
              {concept}
            </Badge>
          </li>
        ))}
      </ul>
    </Section>
  )
}

/** One titled part of the sheet; also for what a caller adds as `children`. */
export function Section({ title, children }: { title: string; children: ReactNode }) {
  const id = useId()
  return (
    <section aria-labelledby={id} className="space-y-2">
      <h3 id={id} className="text-xs font-medium text-muted-foreground">
        {title}
      </h3>
      {children}
    </section>
  )
}
