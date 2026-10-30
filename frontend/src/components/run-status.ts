import type { RunStatus } from '@/api/runs'
import type { StatusTone } from './StatusLabel'

/** Each Construction Run status's name and tone: the one map every run view uses. */
export const RUN_STATUSES: Record<RunStatus, { label: string; tone: StatusTone }> = {
  running: { label: 'Running', tone: 'running' },
  finished: { label: 'Finished', tone: 'success' },
  failed: { label: 'Failed', tone: 'failure' },
}
