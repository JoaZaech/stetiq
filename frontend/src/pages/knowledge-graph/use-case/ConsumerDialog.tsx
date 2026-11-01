import { useState, type ReactNode } from 'react'
import { useSaveUseCase, type Consumer, type SavedUseCase, type UseCase } from '@/api/use-cases'
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
import {
  consumerDraftOf,
  EMPTY_CONSUMER_DRAFT,
  validateConsumerDraft,
  withConsumer,
  type ConsumerDraft,
  type ConsumerDraftErrors,
  type ConsumerDraftField,
} from './consumer-form'
import { Field } from './form-field'

interface ConsumerDialogProps {
  knowledgeGraph: string
  /** The latest Use Case Version's Use Case, which the edit applies to. */
  useCase: UseCase
  /** The Consumer to edit; without it the dialog adds one. */
  consumer?: Consumer
  trigger: ReactNode
  onSaved: (saved: SavedUseCase) => void
}

/**
 * Add or edit one Consumer (its Tasks are edited on their own), then save the complete
 * edited Use Case as a new Use Case Version. An existing Consumer's id is read-only.
 */
export function ConsumerDialog({ knowledgeGraph, useCase, consumer, trigger, onSaved }: ConsumerDialogProps) {
  const [open, setOpen] = useState(false)
  const [draft, setDraft] = useState<ConsumerDraft>(EMPTY_CONSUMER_DRAFT)
  const [errors, setErrors] = useState<ConsumerDraftErrors>({})
  const saving = useSaveUseCase(knowledgeGraph, (saved) => {
    setOpen(false)
    onSaved(saved)
  })

  const onOpenChange = (next: boolean) => {
    if (next) {
      setDraft(consumer ? consumerDraftOf(consumer) : EMPTY_CONSUMER_DRAFT)
      setErrors({})
      saving.reset()
    }
    setOpen(next)
  }

  const field = (name: ConsumerDraftField) => ({
    value: draft[name],
    error: errors[name],
    onChange: (value: string) => setDraft((d) => ({ ...d, [name]: value })),
  })

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogTrigger asChild>{trigger}</DialogTrigger>
      <DialogContent className="sm:max-w-xl">
        <form
          className="grid gap-4"
          noValidate
          onSubmit={(event) => {
            event.preventDefault()
            const invalid = validateConsumerDraft(draft, useCase, consumer?.id)
            setErrors(invalid)
            if (Object.keys(invalid).length) return
            saving.mutate(withConsumer(useCase, draft))
          }}
        >
          <DialogHeader>
            <DialogTitle>{consumer ? `Edit Consumer ${consumer.id}` : 'Add Consumer'}</DialogTitle>
            <DialogDescription>
              A Consumer uses the Knowledge Graph downstream. Saving registers a new Use Case Version.
            </DialogDescription>
          </DialogHeader>
          <Field
            label="Id"
            hint={
              consumer
                ? 'Locked once the Consumer exists: to change it, remove the Consumer and add a new one.'
                : 'Unique among the Consumers, Tasks and Competency Questions of the Use Case.'
            }
            {...field('id')}
          >
            {(props) => <Input {...props} readOnly={consumer !== undefined} className="font-mono" autoFocus={!consumer} />}
          </Field>
          <Field label="Name" {...field('name')}>
            {(props) => <Input {...props} autoFocus={consumer !== undefined} />}
          </Field>
          <Field label="Kind" hint="Optional. An application, an agent, a dashboard, a team…" {...field('kind')}>
            {(props) => <Input {...props} />}
          </Field>
          <Field label="Contact" hint="Optional. Whom to ask about it, by name." {...field('contact')}>
            {(props) => <Input {...props} />}
          </Field>
          <Field label="Description" hint="Optional." {...field('description')}>
            {(props) => <Textarea {...props} className="min-h-16" />}
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
