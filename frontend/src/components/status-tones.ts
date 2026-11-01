import { CircleAlert, CircleCheck, CircleDashed, CircleX, LoaderCircle, TriangleAlert } from 'lucide-react'

/**
 * How a status reads at a glance; each tone has one icon and colour app-wide, so a status
 * never relies on colour alone. `warning` needs attention but is not a failure (e.g.
 * Drift); `neutral` is unknown or not judged (e.g. "Can't check", "Not gated").
 */
export type StatusTone = 'success' | 'failure' | 'error' | 'warning' | 'running' | 'neutral'

export const STATUS_TONES = {
  success: { Icon: CircleCheck, className: 'text-success' },
  failure: { Icon: CircleX, className: 'text-destructive' },
  error: { Icon: TriangleAlert, className: 'text-destructive' },
  warning: { Icon: CircleAlert, className: 'text-warning' },
  running: { Icon: LoaderCircle, className: 'text-primary' },
  neutral: { Icon: CircleDashed, className: 'text-muted-foreground' },
} as const satisfies Record<StatusTone, { Icon: unknown; className: string }>
