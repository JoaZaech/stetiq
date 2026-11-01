import { useId, useState, type ReactNode } from 'react'
import { useSaveUseCase, type Consumer, type SavedUseCase, type Task, type UseCase } from '@/api/use-cases'
import { ErrorAlert } from '@/components/ErrorAlert'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
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
import { Label } from '@/components/ui/label'
import {
  EMPTY_TASK_DRAFT,
  taskDraftOf,
  validateTaskDraft,
  withTask,
  type TaskDraft,
  type TaskDraftErrors,
} from './consumer-form'
import { Field } from './form-field'

interface TaskDialogProps {
  knowledgeGraph: string
  /** The latest Use Case Version's Use Case, which the edit applies to. */
  useCase: UseCase
  /** The Consumer that performs the Task. */
  consumer: Consumer
  /** The Task to edit; without it the dialog adds one to `consumer`. */
  task?: Task
  trigger: ReactNode
  onSaved: (saved: SavedUseCase) => void
}

/**
 * Add or edit one Task of a Consumer, with the Competency Questions it needs picked from
 * the Use Case's, then save the complete edited Use Case as a new Use Case Version. An
 * existing Task's id is read-only.
 */
export function TaskDialog({ knowledgeGraph, useCase, consumer, task, trigger, onSaved }: TaskDialogProps) {
  const [open, setOpen] = useState(false)
  const [draft, setDraft] = useState<TaskDraft>(EMPTY_TASK_DRAFT)
  const [errors, setErrors] = useState<TaskDraftErrors>({})
  const needsId = useId()
  const saving = useSaveUseCase(knowledgeGraph, (saved) => {
    setOpen(false)
    onSaved(saved)
  })

  const onOpenChange = (next: boolean) => {
    if (next) {
      setDraft(task ? taskDraftOf(task) : EMPTY_TASK_DRAFT)
      setErrors({})
      saving.reset()
    }
    setOpen(next)
  }

  const text = (name: 'id' | 'description') => ({
    value: draft[name],
    error: errors[name],
    onChange: (value: string) => setDraft((d) => ({ ...d, [name]: value })),
  })

  const setNeeded = (id: string, needed: boolean) =>
    setDraft((d) => ({
      ...d,
      competency_questions: needed
        ? [...d.competency_questions, id]
        : d.competency_questions.filter((q) => q !== id),
    }))

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogTrigger asChild>{trigger}</DialogTrigger>
      <DialogContent className="sm:max-w-xl">
        <form
          className="grid gap-4"
          noValidate
          onSubmit={(event) => {
            event.preventDefault()
            const invalid = validateTaskDraft(draft, useCase, task?.id)
            setErrors(invalid)
            if (Object.keys(invalid).length) return
            saving.mutate(withTask(useCase, consumer.id, draft))
          }}
        >
          <DialogHeader>
            <DialogTitle>{task ? `Edit Task ${task.id}` : `Add Task to ${consumer.name}`}</DialogTitle>
            <DialogDescription>
              A piece of work {consumer.name} performs with the Knowledge Graph. Saving registers a new
              Use Case Version.
            </DialogDescription>
          </DialogHeader>
          <Field
            label="Id"
            hint={
              task
                ? 'Locked once the Task exists: to change it, remove the Task and add a new one.'
                : 'Unique among the Consumers, Tasks and Competency Questions of the Use Case.'
            }
            {...text('id')}
          >
            {(props) => <Input {...props} readOnly={task !== undefined} className="font-mono" autoFocus={!task} />}
          </Field>
          <Field label="Description" {...text('description')}>
            {(props) => <Input {...props} autoFocus={task !== undefined} />}
          </Field>
          <fieldset aria-labelledby={needsId} className="grid gap-2">
            <legend id={needsId} className="text-sm font-medium">
              Competency Questions it needs
            </legend>
            <ul className="grid max-h-64 gap-2 overflow-y-auto">
              {useCase.competency_questions.map((q) => {
                const checkboxId = `${needsId}-${q.id}`
                return (
                  <li key={q.id} className="flex items-start gap-2">
                    <Checkbox
                      id={checkboxId}
                      className="mt-0.5"
                      checked={draft.competency_questions.includes(q.id)}
                      onCheckedChange={(checked) => setNeeded(q.id, checked === true)}
                    />
                    <Label htmlFor={checkboxId} className="font-normal">
                      <code className="font-mono text-xs">{q.id}</code>
                      <span className="text-muted-foreground">{q.question}</span>
                    </Label>
                  </li>
                )
              })}
            </ul>
          </fieldset>
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
