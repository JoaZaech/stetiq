import type { RunStatus } from '@/api/runs'
import { RUN_STATUSES } from './run-status'
import { StatusLabel } from './StatusLabel'

/** A Construction Run status as an icon and its name. */
export function RunStatusLabel({ status }: { status: RunStatus }) {
  return <StatusLabel {...RUN_STATUSES[status]} />
}
