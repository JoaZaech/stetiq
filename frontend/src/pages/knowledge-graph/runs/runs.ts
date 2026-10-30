import type { ConstructionRun } from '@/api/runs'

/** A run id as the run table shows it; the full id is on the run page (and copyable). */
export const shortRunId = (id: string) => id.slice(0, 8)

/** Milliseconds from start to end, or to `now` while the run is running. */
export function runDurationMs(run: ConstructionRun, now: number): number {
  const end = run.ended_at === null ? now : Date.parse(run.ended_at)
  return Math.max(0, end - Date.parse(run.started_at))
}

/** e.g. "850 ms", "4.2 s", "3 min 4 s", "2 h 5 min". */
export function formatDuration(ms: number): string {
  if (ms < 1000) return `${Math.round(ms)} ms`
  const seconds = ms / 1000
  if (seconds < 60) return `${seconds.toFixed(1)} s`
  const s = Math.floor(seconds)
  const minutes = Math.floor(s / 60)
  if (minutes < 60) return `${minutes} min ${s % 60} s`
  return `${Math.floor(minutes / 60)} h ${minutes % 60} min`
}

export const RUN_STATUS_FILTERS = ['all', 'running', 'finished', 'failed'] as const
export type RunStatusFilter = (typeof RUN_STATUS_FILTERS)[number]

/** Time ranges of the run table, by how far back a run may have started. */
export const RUN_TIME_RANGES = [
  { value: 'all', label: 'All time', ms: Infinity },
  { value: '24h', label: 'Last 24 hours', ms: 24 * 3600_000 },
  { value: '7d', label: 'Last 7 days', ms: 7 * 24 * 3600_000 },
  { value: '30d', label: 'Last 30 days', ms: 30 * 24 * 3600_000 },
] as const
export type RunTimeRange = (typeof RUN_TIME_RANGES)[number]['value']

export interface RunFilters {
  status: RunStatusFilter
  range: RunTimeRange
}

/** The filters in a run list URL (`?status=failed&range=7d`); unknown values mean "all". */
export function parseRunFilters(params: URLSearchParams): RunFilters {
  const status = params.get('status')
  const range = params.get('range')
  return {
    status: RUN_STATUS_FILTERS.find((s) => s === status) ?? 'all',
    range: RUN_TIME_RANGES.find((r) => r.value === range)?.value ?? 'all',
  }
}

/** The runs that match the filters: their status, and started within the range before `now`. */
export function filterRuns(
  runs: readonly ConstructionRun[],
  { status, range }: RunFilters,
  now: number,
): ConstructionRun[] {
  const within = RUN_TIME_RANGES.find((r) => r.value === range)?.ms ?? Infinity
  return runs.filter(
    (run) =>
      (status === 'all' || run.status === status) &&
      now - Date.parse(run.started_at) <= within,
  )
}

/** Every param and metric key over the runs, sorted: the run table's optional columns. */
export function runKeys(runs: readonly ConstructionRun[]): { params: string[]; metrics: string[] } {
  const sorted = (keys: Iterable<string>) => [...new Set(keys)].sort((a, b) => a.localeCompare(b))
  return {
    params: sorted(runs.flatMap((r) => Object.keys(r.params))),
    metrics: sorted(runs.flatMap((r) => Object.keys(r.metrics))),
  }
}

/**
 * How a run ended, for its page: still `running`, `finished`, `failed` before its Graph
 * Source was observed (aborted, or the Observation itself failed), or `strict`: it
 * observed Concepts its Declared Ontology lacks and the Evolution Mode is strict, so it
 * failed instead of giving rise to a Candidate (`TrackingService.end_run`).
 */
export type RunOutcome = 'running' | 'finished' | 'failed' | 'strict'

export function runOutcome(run: ConstructionRun): RunOutcome {
  if (run.status !== 'failed') return run.status
  return run.observation_id === null ? 'failed' : 'strict'
}
