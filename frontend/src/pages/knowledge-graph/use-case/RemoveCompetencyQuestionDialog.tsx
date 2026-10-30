import { useState, type ReactNode } from 'react'
import { useSaveUseCase, type CompetencyQuestion, type SavedUseCase, type UseCase } from '@/api/use-cases'
import { ErrorAlert } from '@/components/ErrorAlert'
import {
  AlertDialog,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from '@/components/ui/alert-dialog'
import { Button } from '@/components/ui/button'
import { withoutQuestion } from './question-form'

interface RemoveCompetencyQuestionDialogProps {
  knowledgeGraph: string
  /** The latest Use Case Version's Use Case, which the removal applies to. */
  useCase: UseCase
  question: CompetencyQuestion
  trigger: ReactNode
  onSaved: (saved: SavedUseCase) => void
}

/** Confirm, then save the Use Case without `question` as a new Use Case Version. */
export function RemoveCompetencyQuestionDialog({
  knowledgeGraph,
  useCase,
  question,
  trigger,
  onSaved,
}: RemoveCompetencyQuestionDialogProps) {
  const [open, setOpen] = useState(false)
  const saving = useSaveUseCase(knowledgeGraph)

  const onOpenChange = (next: boolean) => {
    if (next) saving.reset()
    setOpen(next)
  }

  return (
    <AlertDialog open={open} onOpenChange={onOpenChange}>
      <AlertDialogTrigger asChild>{trigger}</AlertDialogTrigger>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>Remove {question.id}?</AlertDialogTitle>
          <AlertDialogDescription>
            “{question.question}” will not be in the new Use Case Version. Earlier versions, and the
            results judged against them, keep it.
          </AlertDialogDescription>
        </AlertDialogHeader>
        {saving.isError && <ErrorAlert error={saving.error} title="Could not remove the question" />}
        <AlertDialogFooter>
          <AlertDialogCancel>Cancel</AlertDialogCancel>
          <Button
            variant="destructive"
            disabled={saving.isPending}
            onClick={() =>
              saving.mutate(withoutQuestion(useCase, question.id), {
                onSuccess: (saved) => {
                  setOpen(false)
                  onSaved(saved)
                },
              })
            }
          >
            {saving.isPending ? 'Removing…' : 'Remove'}
          </Button>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  )
}
