import { useState } from 'react'
import { Pencil } from 'lucide-react'
import { useSetKnowledgeGraphDescription } from '@/api/knowledge-graph'
import { ErrorAlert } from '@/components/ErrorAlert'
import { Markdown } from '@/components/Markdown'
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
import { Label } from '@/components/ui/label'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Textarea } from '@/components/ui/textarea'

interface EditDescriptionDialogProps {
  name: string
  description: string | null
  disabled: boolean
}

/** The Edit action of the Knowledge Graph header: a markdown editor with a preview. */
export function EditDescriptionDialog({ name, description, disabled }: EditDescriptionDialogProps) {
  const [open, setOpen] = useState(false)
  const [draft, setDraft] = useState('')
  const saving = useSetKnowledgeGraphDescription(name)

  const onOpenChange = (next: boolean) => {
    if (next) {
      setDraft(description ?? '')
      saving.reset()
    }
    setOpen(next)
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogTrigger asChild>
        <Button variant="outline" size="sm" disabled={disabled}>
          <Pencil />
          Edit description
        </Button>
      </DialogTrigger>
      <DialogContent className="sm:max-w-2xl">
        <form
          className="grid gap-4"
          onSubmit={(event) => {
            event.preventDefault()
            saving.mutate(draft, { onSuccess: () => setOpen(false) })
          }}
        >
          <DialogHeader>
            <DialogTitle>Edit description</DialogTitle>
            <DialogDescription>
              What {name} is for, in markdown. Everyone who can read it sees this in its header.
            </DialogDescription>
          </DialogHeader>
          <Tabs defaultValue="write">
            <TabsList>
              <TabsTrigger value="write">Write</TabsTrigger>
              <TabsTrigger value="preview">Preview</TabsTrigger>
            </TabsList>
            <TabsContent value="write" className="grid gap-2">
              <Label htmlFor="kg-description" className="sr-only">
                Description
              </Label>
              <Textarea
                id="kg-description"
                value={draft}
                onChange={(event) => setDraft(event.target.value)}
                className="max-h-96 min-h-48 font-mono"
                placeholder="What this Knowledge Graph is for…"
                autoFocus
              />
            </TabsContent>
            <TabsContent value="preview" className="max-h-96 min-h-48 overflow-y-auto rounded-lg border p-3">
              {draft.trim() ? (
                <Markdown>{draft}</Markdown>
              ) : (
                <p className="text-sm text-muted-foreground italic">No description</p>
              )}
            </TabsContent>
          </Tabs>
          {saving.isError && <ErrorAlert error={saving.error} title="Could not save the description" />}
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
