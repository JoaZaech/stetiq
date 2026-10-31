import { useState, type ReactNode } from 'react'
import { ApiError } from '@/api/client'
import { useSaveUseCase, type CompetencyQuestion, type SavedUseCase, type UseCase } from '@/api/use-cases'
import { ErrorAlert } from '@/components/ErrorAlert'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { Field } from './form-field'
import {
  draftOf,
  EMPTY_DRAFT,
  questionOf,
  serverErrorField,
  validateDraft,
  withQuestion,
  type DraftErrors,
  type DraftField,
  type QuestionDraft,
} from './question-form'

interface CompetencyQuestionDialogProps {
  knowledgeGraph: string
  /** The latest Use Case Version's Use Case, which the edit applies to. */
  useCase: UseCase
  /** The question to edit; without it the dialog adds one. */
  question?: CompetencyQuestion
  /** The button that opens the dialog. */
  trigger: ReactNode
  onSaved: (saved: SavedUseCase) => void
}

/**
 * Add or edit one Competency Question, then save the complete edited Use Case as a new
 * Use Case Version. An existing question's id is read-only: changing it is a removal
 * plus an addition.
 */
export function CompetencyQuestionDialog({
  knowledgeGraph,
  useCase,
  question,
  trigger,
  onSaved,
}: CompetencyQuestionDialogProps) {
  const [open, setOpen] = useState(false)
  const [draft, setDraft] = useState<QuestionDraft>(EMPTY_DRAFT)
  const [errors, setErrors] = useState<DraftErrors>({})
  const saving = useSaveUseCase(knowledgeGraph, (saved) => {
    setOpen(false)
    onSaved(saved)
  })
  const title = question ? `Edit ${question.id}` : 'Add Competency Question'

  const onOpenChange = (next: boolean) => {
    if (next) {
      setDraft(question ? draftOf(question) : EMPTY_DRAFT)
      setErrors({})
      saving.reset()
    }
    setOpen(next)
  }

  const field = (name: DraftField) => ({
    value: draft[name],
    error: errors[name],
    onChange: (value: string) => setDraft((d) => ({ ...d, [name]: value })),
  })

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogTrigger asChild>{trigger}</DialogTrigger>
      <DialogContent className="sm:max-w-2xl">
        <form
          className="grid gap-4"
          noValidate
          onSubmit={(event) => {
            event.preventDefault()
            const otherIds = useCase.competency_questions
              .map((q) => q.id)
              .filter((id) => id !== question?.id)
            const invalid = validateDraft(draft, otherIds)
            setErrors(invalid)
            if (Object.keys(invalid).length) return
            saving.mutate(withQuestion(useCase, questionOf(draft)), {
              onError: (error) => {
                // The server re-validates: put what it refuses on its field too.
                const field = error instanceof ApiError ? serverErrorField(error.message) : undefined
                if (field) setErrors({ [field]: error.message })
              },
            })
          }}
        >
          <DialogHeader>
            <DialogTitle>{title}</DialogTitle>
            <DialogDescription>
              Saving registers a new Use Case Version, so earlier results stay tied to the version
              they were judged against.
            </DialogDescription>
          </DialogHeader>
          <Field
            label="Id"
            hint={question ? 'Locked once the question exists: to change it, remove the question and add a new one.' : undefined}
            {...field('id')}
          >
            {(props) => <Input {...props} readOnly={question !== undefined} className="font-mono" autoFocus={!question} />}
          </Field>
          <Field label="Question" {...field('question')}>
            {(props) => <Input {...props} autoFocus={question !== undefined} />}
          </Field>
          <Field label="Cypher query" hint="Optional." {...field('query')}>
            {(props) => <Textarea {...props} className="min-h-20 font-mono text-xs" />}
          </Field>
          <Field label="Expected answer" hint="Optional. Any JSON value the query's rows must match." {...field('expected_answer')}>
            {(props) => <Textarea {...props} className="min-h-20 font-mono text-xs" />}
          </Field>
          <Field
            label="Concept mapping"
            hint="Optional. One Concept reference per line: Customer, Ticket.opened_at, (Customer)-[OPENED]->(Ticket)."
            {...field('concepts')}
          >
            {(props) => <Textarea {...props} className="min-h-16 font-mono text-xs" />}
          </Field>
          {saving.isError && <ErrorAlert error={saving.error} title="Could not save the Use Case" />}
          <DialogFooter>
            <DialogClose asChild>
              <Button type="button" variant="outline">
                Cancel
              </Button>
            </DialogClose>
            <Button type="submit" disabled={saving.isPending}>
              {saving.isPending ? 'Saving…' : 'Save'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
