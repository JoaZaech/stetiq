import { CircleCheck, CircleX, LoaderCircle } from 'lucide-react'
import type { RunStatus } from '@/api/knowledge-graphs'

const STATUS = {
  running: { label: 'Running', Icon: LoaderCircle, className: 'text-primary' },
  finished: { label: 'Finished', Icon: CircleCheck, className: 'text-emerald-600 dark:text-emerald-500' },
  failed: { label: 'Failed', Icon: CircleX, className: 'text-destructive' },
} as const

/** A Construction Run status as an icon and its name. */
export function RunStatusLabel({ status }: { status: RunStatus }) {
  const { label, Icon, className } = STATUS[status]
  return (
    <span className="inline-flex items-center gap-1.5">
      <Icon aria-hidden className={`size-4 ${className}`} />
      {label}
    </span>
  )
}
