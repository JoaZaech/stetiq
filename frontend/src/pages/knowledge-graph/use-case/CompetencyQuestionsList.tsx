import { useMemo } from 'react'
import type { CompetencyQuestion, UseCaseVersion } from '@/api/use-cases'
import { ErrorAlert } from '@/components/ErrorAlert'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import { AnswerabilityLabel } from './AnswerabilityLabel'
import type { AnswerabilityStatus } from './answerability'
import { useLatestAnswerability, type LatestAnswerability } from './latest-answerability'
import { questionsServingNoTask } from './readiness'

interface CompetencyQuestionsListProps {
  knowledgeGraph: string
  version: UseCaseVersion
  /** Opens the question's sheet. */
  onOpen: (question: CompetencyQuestion) => void
}

/**
 * A Use Case Version's Competency Questions, sorted by id: each question's text and its
 * answerability on the latest Ontology Version, under a summary line, and marked when
 * no Task needs it. A row opens the question's sheet, which holds everything else.
 */
export function CompetencyQuestionsList({ knowledgeGraph, version, onOpen }: CompetencyQuestionsListProps) {
  const useCase = version.use_case
  const latest = useLatestAnswerability(knowledgeGraph, version.number)
  const servingNoTask = useMemo(() => questionsServingNoTask(useCase), [useCase])
  const status = useMemo(
    () =>
      new Map<string, AnswerabilityStatus>(
        latest.state === 'judged' ? latest.answerability.rows.map((row) => [row.id, row.status]) : [],
      ),
    [latest],
  )
  if (useCase.competency_questions.length === 0) {
    return <p className="text-sm text-muted-foreground">This Use Case Version has no Competency Questions.</p>
  }
  return (
    <div className="space-y-2">
      <Summary latest={latest} useCaseVersion={version.number} />
      <ul aria-label="Competency Questions" className="divide-y overflow-hidden rounded-lg border">
        {useCase.competency_questions.map((question) => {
          const answerability = status.get(question.id)
          return (
            <li key={question.id}>
              <button
                type="button"
                onClick={() => onOpen(question)}
                className="flex w-full flex-wrap items-center gap-x-3 gap-y-1 px-3 py-2 text-left text-sm hover:bg-muted/50 focus-visible:bg-muted/50 focus-visible:outline-none"
              >
                <span className="min-w-0 flex-1">{question.question}</span>
                {servingNoTask.has(question.id) && (
                  <Badge variant="outline" className="text-muted-foreground">
                    Not used by any Task
                  </Badge>
                )}
                {answerability && <AnswerabilityLabel status={answerability} />}
              </button>
            </li>
          )
        })}
      </ul>
    </div>
  )
}

/** How many of the questions the latest Ontology Version answers, or why that isn't known. */
function Summary({ latest, useCaseVersion }: { latest: LatestAnswerability; useCaseVersion: number }) {
  switch (latest.state) {
    case 'error':
      return <ErrorAlert error={latest.error} />
    case 'pending':
      return <Skeleton className="h-5 w-80" />
    case 'no-ontology':
      return <p className="text-sm text-muted-foreground">This Knowledge Graph has no Ontology Version yet.</p>
    case 'not-judged':
      return (
        <p className="text-sm text-muted-foreground">
          Ontology Version v{latest.ontologyVersion} has not been judged against Use Case Version{' '}
          {useCaseVersion} yet. Saving a change to the Competency Questions judges it.
        </p>
      )
    case 'judged':
      return (
        <p className="text-sm">
          Ontology Version v{latest.ontologyVersion} answers {latest.answerability.answerable} of{' '}
          {latest.answerability.questions} Competency Questions.
        </p>
      )
  }
}
