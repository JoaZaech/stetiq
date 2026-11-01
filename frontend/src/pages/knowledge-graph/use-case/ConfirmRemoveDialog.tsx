import { useState, type ReactNode } from 'react'
import { useSaveUseCase, type SavedUseCase, type Task, type UseCase } from '@/api/use-cases'
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

interface ConfirmRemoveDialogProps {
  knowledgeGraph: string
  /** "Remove …?" */
  title: string
  /** What the removal does, under the title. */
  description: ReactNode
  /** More detail, such as the Tasks the removal affects. */
  children?: ReactNode
  /** The Use Case without what is removed, saved on confirming. */
  next: () => UseCase
  trigger: ReactNode
  onSaved: (saved: SavedUseCase) => void
}

/** Confirm, then save `next()` as a new Use Case Version. */
export function ConfirmRemoveDialog({
  knowledgeGraph,
  title,
  description,
  children,
  next,
  trigger,
  onSaved,
}: ConfirmRemoveDialogProps) {
  const [open, setOpen] = useState(false)
  const saving = useSaveUseCase(knowledgeGraph, (saved) => {
    setOpen(false)
    onSaved(saved)
  })

  const onOpenChange = (opening: boolean) => {
    if (opening) saving.reset()
    setOpen(opening)
  }

  return (
    <AlertDialog open={open} onOpenChange={onOpenChange}>
      <AlertDialogTrigger asChild>{trigger}</AlertDialogTrigger>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>{title}</AlertDialogTitle>
          <AlertDialogDescription>{description}</AlertDialogDescription>
        </AlertDialogHeader>
        {children}
        {saving.isError && <ErrorAlert error={saving.error} title="Could not save the Use Case" />}
        <AlertDialogFooter>
          <AlertDialogCancel>Cancel</AlertDialogCancel>
          <Button variant="destructive" disabled={saving.isPending} onClick={() => saving.mutate(next())}>
            {saving.isPending ? 'Removing…' : 'Remove'}
          </Button>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  )
}

/** A list of Tasks, by id and description, named `label`. */
export function TaskList({ label, tasks }: { label: string; tasks: Task[] }) {
  return (
    <ul aria-label={label} className="space-y-1 text-sm">
      {tasks.map((task) => (
        <li key={task.id}>
          <code className="font-mono text-xs">{task.id}</code>{' '}
          <span className="text-muted-foreground">{task.description}</span>
        </li>
      ))}
    </ul>
  )
}
