import { CircleAlert } from 'lucide-react'
import { errorTitle } from '@/api/client'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'

/**
 * A readable message for a failed request, so a failing server never looks like empty
 * data. A refused write (403) is titled "Access denied", whatever `title` says.
 */
export function ErrorAlert({ error, title = 'Something went wrong' }: { error: unknown; title?: string }) {
  const message = error instanceof Error ? error.message : String(error)
  return (
    <Alert variant="destructive">
      <CircleAlert />
      <AlertTitle>{errorTitle(error, title)}</AlertTitle>
      <AlertDescription>{message}</AlertDescription>
    </Alert>
  )
}
