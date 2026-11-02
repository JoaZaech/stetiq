import { type GatePreview, runGatePreview } from '@/api/gate-previews'
import { type GateResult, latestGateResult } from '@/api/gate-results'
import type { DriftEvent } from '@/api/observations'
import type { EvaluationResult } from '@/api/ontology-versions'
import type { ConstructionRun } from '@/api/runs'
import type { StatusTone } from '@/components/StatusLabel'
import type { EvaluationInputs } from '../evaluation/evaluation-kpis'

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

/**
 * Params the run table shows as columns from the start, in this order, when any run
 * logged them; the rest are added with Columns. `sources` reads as a count.
 */
export const DEFAULT_PARAM_COLUMNS = ['extractor', 'model', 'sources'] as const

/** The `DEFAULT_PARAM_COLUMNS` some run logged, and every other param key, for Columns. */
export function splitParamKeys(keys: readonly string[]): { shown: string[]; optional: string[] } {
  const defaults: readonly string[] = DEFAULT_PARAM_COLUMNS
  return {
    shown: DEFAULT_PARAM_COLUMNS.filter((k) => keys.includes(k)),
    optional: keys.filter((k) => !defaults.includes(k)),
  }
}

/** A `sources` param's entries: `machines.csv, reports/` → `['machines.csv', 'reports/']`. */
export function sourceList(value: string): string[] {
  return value
    .split(',')
    .map((s) => s.trim())
    .filter(Boolean)
}

/** What the run list's search matches: the run id, its param values and its versions. */
export function runSearchFields(run: ConstructionRun): (string | null)[] {
  return [
    run.id,
    ...Object.values(run.params),
    `v${run.ontology_version}`,
    run.candidate_version === null ? null : `v${run.candidate_version}`,
  ]
}

/**
 * A failed run's banner, one line: what failed and, for a strict run with a Conformance,
 * the finding its Evaluation tab opens filtered to. `null` for a run that did not fail.
 */
export function runFailure(run: ConstructionRun): { text: string; finding: string | null } | null {
  const outcome = runOutcome(run)
  if (outcome === 'failed') return { text: 'Failed before the Graph Source was observed.', finding: null }
  if (outcome !== 'strict') return null
  const undeclared = run.conformance?.mismatches.filter((m) => m.kind === 'undeclared' && m.subject_kind !== 'pattern')
  if (!undeclared?.length) return { text: 'Failed: Concepts observed but not declared (strict mode).', finding: null }
  const n = undeclared.length
  return {
    text: `Failed: ${n} ${n === 1 ? 'Concept' : 'Concepts'} observed but not declared (strict mode).`,
    finding: 'Observed but not declared',
  }
}

/** `evaluation.run.CQ_EXECUTION_EVALUATOR`: executes the Use Case's Competency Questions. */
export const CQ_EXECUTION_EVALUATOR = 'competency_question_execution'

/**
 * One executed Competency Question, from a Detail of the execution Evaluator. Only
 * these fields are read: the verdict, which check judged it and an exception type.
 * Rows are never stored (ADR 0001), and the UI shows nothing else from the Detail.
 */
export interface ExecutedQuestion {
  id: string
  status: 'passed' | 'failed' | 'error'
  check: 'non_empty' | 'expected_answer'
  error: string | null
}

export function executedQuestions(result: EvaluationResult): ExecutedQuestion[] {
  return result.details.map((detail) => {
    const data = detail.data ?? {}
    return {
      id: detail.item,
      status: data.status as ExecutedQuestion['status'],
      check: data.check as ExecutedQuestion['check'],
      error: typeof data.error === 'string' ? data.error : null,
    }
  })
}

/**
 * A run's four evaluation KPIs: its Conformance score; the Competency Questions it
 * executed that passed, of all it executed; its latest recorded Gate result's Gates
 * passed, of all; and the Drift findings of the Observation it ended with (0 when that
 * Observation found no Drift, none when the run ended without one or while loading).
 */
export function runEvaluationInputs(
  run: ConstructionRun,
  evaluations: readonly EvaluationResult[] | undefined,
  gateResults: readonly GateResult[] | undefined,
  driftEvents: readonly DriftEvent[] | undefined,
): EvaluationInputs {
  const execution = evaluations?.find((r) => r.evaluator === CQ_EXECUTION_EVALUATOR)
  const questions = execution ? executedQuestions(execution) : []
  const gate = gateResults && latestGateResult(gateResults, 'construction_run', run.id)
  const drift = driftEvents?.find((e) => e.observation_id === run.observation_id)
  return {
    conformance: run.conformance?.score ?? null,
    coverage: questions.length
      ? { count: questions.filter((q) => q.status === 'passed').length, total: questions.length }
      : null,
    gates: gate ? { count: gate.outcomes.filter((o) => o.passed).length, total: gate.outcomes.length } : null,
    drift: run.observation_id === null || driftEvents === undefined ? null : (drift?.findings.length ?? 0),
  }
}

/**
 * A Conformance score's colour, by how close it is to 100 %, as a status tone:
 * `success` from 95 %, `warning` from 80 %, `failure` below.
 */
export function conformanceTone(score: number): StatusTone {
  if (score >= 0.95) return 'success'
  if (score >= 0.8) return 'warning'
  return 'failure'
}

/**
 * What a run's Gate column shows: its latest `recorded` Gate result; else its Gate
 * `preview`, which is never recorded (ADR 0007); else `none`.
 */
export type RunGate = { kind: 'recorded' | 'preview'; passed: boolean } | { kind: 'none' }

export function runGate(runId: string, results: readonly GateResult[], previews: readonly GatePreview[]): RunGate {
  const recorded = latestGateResult(results, 'construction_run', runId)
  if (recorded) return { kind: 'recorded', passed: recorded.passed }
  const preview = runGatePreview(previews, runId)
  if (preview) return { kind: 'preview', passed: preview.passed }
  return { kind: 'none' }
}
