import { STATUS_TONES, type StatusTone } from './status-tones'

export type { StatusTone } from './status-tones'

/** A status as its tone's icon and its name, e.g. a run's "Finished" or a check's "Passed". */
export function StatusLabel({ tone, label }: { tone: StatusTone; label: string }) {
  const { Icon, className } = STATUS_TONES[tone]
  return (
    <span className="inline-flex items-center gap-1.5">
      <Icon aria-hidden className={`size-4 ${className}`} />
      {label}
    </span>
  )
}

/** A status as its tone's icon alone, named `label` for screen readers and on hover. */
export function StatusIcon({ tone, label }: { tone: StatusTone; label: string }) {
  const { Icon, className } = STATUS_TONES[tone]
  return (
    <span role="img" aria-label={label} title={label} className="inline-flex shrink-0">
      <Icon aria-hidden className={`size-4 ${className}`} />
    </span>
  )
}
