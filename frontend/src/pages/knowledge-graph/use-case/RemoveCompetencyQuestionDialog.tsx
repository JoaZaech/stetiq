import type { ReactNode } from 'react'
import type { CompetencyQuestion, SavedUseCase, UseCase } from '@/api/use-cases'
import { ConfirmRemoveDialog, TaskList } from './ConfirmRemoveDialog'
import { tasksNeeding, withoutQuestion } from './question-form'

interface RemoveCompetencyQuestionDialogProps {
  knowledgeGraph: string
  /** The latest Use Case Version's Use Case, which the removal applies to. */
  useCase: UseCase
  question: CompetencyQuestion
  trigger: ReactNode
  onSaved: (saved: SavedUseCase) => void
}

/**
 * Confirm, naming the Tasks that need `question`, then save the Use Case without it (and
 * without it on those Tasks) as a new Use Case Version.
 */
export function RemoveCompetencyQuestionDialog({
  knowledgeGraph,
  useCase,
  question,
  trigger,
  onSaved,
}: RemoveCompetencyQuestionDialogProps) {
  const losing = tasksNeeding(useCase, question.id)
  return (
    <ConfirmRemoveDialog
      knowledgeGraph={knowledgeGraph}
      title={`Remove ${question.id}?`}
      description={
        <>
          “{question.question}” will not be in the new Use Case Version. Earlier versions, and the
          results judged against them, keep it.
        </>
      }
      next={() => withoutQuestion(useCase, question.id)}
      trigger={trigger}
      onSaved={onSaved}
    >
      {losing.length > 0 && (
        <div className="space-y-1">
          <p className="text-sm">
            {losing.length === 1 ? 'This Task needs it and loses it:' : 'These Tasks need it and lose it:'}
          </p>
          <TaskList label="Tasks that lose it" tasks={losing} />
        </div>
      )}
    </ConfirmRemoveDialog>
  )
}
