import { CircleCheck, CircleX, LoaderCircle, TriangleAlert } from 'lucide-react'

/** How a status reads at a glance; each tone has one icon and colour app-wide. */
export type StatusTone = 'success' | 'failure' | 'error' | 'running'

const TONES = {
  success: { Icon: CircleCheck, className: 'text-success' },
  failure: { Icon: CircleX, className: 'text-destructive' },
  error: { Icon: TriangleAlert, className: 'text-destructive' },
  running: { Icon: LoaderCircle, className: 'text-primary' },
} as const

/** A status as its tone's icon and its name, e.g. a run's "Finished" or a check's "Passed". */
export function StatusLabel({ tone, label }: { tone: StatusTone; label: string }) {
  const { Icon, className } = TONES[tone]
  return (
    <span className="inline-flex items-center gap-1.5">
      <Icon aria-hidden className={`size-4 ${className}`} />
      {label}
    </span>
  )
}
