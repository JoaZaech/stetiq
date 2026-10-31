import { type GatePreview, runGatePreview } from '@/api/gate-previews'
import { type GateResult, latestGateResult } from '@/api/gate-results'
import type { EvaluationResult } from '@/api/ontology-versions'
import type { ConstructionRun } from '@/api/runs'
import { formatMetric } from '@/lib/format'
import { type MetricPoint, type MetricSeries, metricSeries } from '@/lib/metric-charts'
import { evaluatorMetricKey, evaluatorMetrics } from '../versions/evaluator-metrics'

/** A compared value; `null` where a run has none (e.g. a param it did not log). */
export type ComparedValue = string | number | null

/** One key across the compared runs: `values[i]` belongs to `runs[i]`. */
export interface ComparisonRow<V extends ComparedValue = ComparedValue> {
  key: string
  values: V[]
}

/**
 * Runs side by side, as `Client.compare_runs` composes them: `values[i]` and
 * `conformance[i]` belong to `runs[i]`.
 */
export interface RunComparison {
  runs: readonly ConstructionRun[]
  declaredOntology: number[]
  candidate: (number | null)[]
  /** Conformance scores; `null` for a run without an Observation. */
  conformance: (number | null)[]
  params: ComparisonRow<string | null>[]
  metrics: ComparisonRow<number | null>[]
  /** The latest run-level Evaluator results, keyed `<evaluator>/<metric>` (`evaluatorMetrics`). */
  evaluations: ComparisonRow<number | null>[]
}

/** One row per key over `records` (one per run), sorted by key. */
function rows<V extends string | number>(records: readonly Readonly<Record<string, V>>[]): ComparisonRow<V | null>[] {
  const keys = [...new Set(records.flatMap((r) => Object.keys(r)))].sort((a, b) => a.localeCompare(b))
  return keys.map((key) => ({ key, values: records.map((r) => r[key] ?? null) }))
}

/** `evaluations[i]` are `runs[i]`'s Evaluator results (the run evaluations route). */
export function compareRuns(
  runs: readonly ConstructionRun[],
  evaluations: readonly (readonly EvaluationResult[])[],
): RunComparison {
  return {
    runs,
    declaredOntology: runs.map((r) => r.ontology_version),
    candidate: runs.map((r) => r.candidate_version),
    conformance: runs.map((r) => r.conformance?.score ?? null),
    params: rows(runs.map((r) => r.params)),
    metrics: rows(runs.map((r) => r.metrics)),
    evaluations: rows(evaluations.map(evaluatorMetrics)),
  }
}

/** Whether the runs' values are not all the same ("Show diff only" keeps these rows). */
export function differs(values: readonly ComparedValue[]): boolean {
  return values.some((v) => v !== values[0])
}

/** The Conformance score's name in the run charts, next to the run metrics. */
export const CONFORMANCE_METRIC = 'Conformance'

/**
 * Each run at its start time, for the run charts, with each kind of KPI apart (so a run
 * metric named like an Evaluator KPI or Conformance is never mixed with it): its run
 * metrics, its Conformance score and its Evaluator results (keyed `<evaluator>/<metric>`,
 * see `evaluatorMetrics`). `evaluations` are the Knowledge Graph-wide run results; each
 * joins its run by `subject_id`.
 */
export function runChartPoints(
  runs: readonly ConstructionRun[],
  evaluations: readonly EvaluationResult[],
): Record<Kpi['kind'], MetricPoint[]> {
  const byRun = new Map<string, EvaluationResult[]>()
  for (const result of evaluations) byRun.set(result.subject_id, [...(byRun.get(result.subject_id) ?? []), result])
  const at = (run: ConstructionRun, metrics: Readonly<Record<string, number>>): MetricPoint => ({
    x: Date.parse(run.started_at),
    id: run.id,
    metrics,
  })
  return {
    'run-metric': runs.map((run) => at(run, run.metrics)),
    conformance: runs.map((run) =>
      at(run, run.conformance === null ? {} : { [CONFORMANCE_METRIC]: run.conformance.score }),
    ),
    evaluator: runs.map((run) => at(run, evaluatorMetrics(byRun.get(run.id) ?? []))),
  }
}

/**
 * A KPI of a run: a run metric the pipeline logged (never gated), its Conformance, or an
 * Evaluator result metric keyed `<evaluator>/<metric>` (see `evaluatorMetrics`).
 */
export type Kpi = { kind: 'run-metric'; key: string } | { kind: 'conformance' } | { kind: 'evaluator'; key: string }

/** One Gate's outcome in a Gate result or Gate Preview, with the Gate's definition. */
export type GateOutcome = GateResult['outcomes'][number]

/** What judges one run: its latest recorded Gate result and its Gate Preview, if any. */
export interface RunGating {
  recorded?: GateResult
  preview?: GatePreview
}

/** What judges the run `runId`: its latest recorded Gate result and its Gate Preview. */
export function runGating(
  runId: string,
  gateResults: readonly GateResult[],
  previews: readonly GatePreview[],
): RunGating {
  return {
    recorded: latestGateResult(gateResults, 'construction_run', runId),
    preview: runGatePreview(previews, runId),
  }
}

/** Where a verdict came from: a Gate result CI recorded, or a Gate Preview. */
export type VerdictOrigin = 'recorded' | 'preview'

/**
 * A run's KPI judged by its Gates. `no-result`: a Gate covers the KPI and failed, and the
 * run has no value for it. `outcomes` are the covering Gates' outcomes.
 */
export type Verdict =
  | { verdict: 'pass' | 'fail' | 'no-result'; origin: VerdictOrigin; outcomes: GateOutcome[] }
  | { verdict: 'ungated' }

/** The Gate result that judges a run: a recorded one always wins over the preview. */
export function judgingGateResult(
  gating: RunGating,
): { origin: VerdictOrigin; result: GateResult | GatePreview } | undefined {
  if (gating.recorded !== undefined) return { origin: 'recorded', result: gating.recorded }
  if (gating.preview !== undefined) return { origin: 'preview', result: gating.preview }
  return undefined
}

/** Whether `gate` judges `kpi`: a conformance Gate covers Conformance, a metric Gate its `<evaluator>/<metric>`. */
function covers(gate: GateOutcome['gate'], kpi: Kpi): boolean {
  if (kpi.kind === 'conformance') return gate.check === 'conformance'
  if (kpi.kind === 'run-metric' || gate.check !== 'metric') return false
  const parameters = (gate.parameters ?? {}) as Record<string, unknown>
  return kpi.key === evaluatorMetricKey(String(gate.evaluator), parameters, String(gate.metric))
}

/** A run's `kpi` (its `value`, `null` when the run has none) judged by `gating`. */
export function kpiVerdict(kpi: Kpi, value: number | null | undefined, gating: RunGating): Verdict {
  const judging = judgingGateResult(gating)
  const outcomes = judging?.result.outcomes.filter((o) => covers(o.gate, kpi)) ?? []
  if (judging === undefined || outcomes.length === 0) return { verdict: 'ungated' }
  const passed = outcomes.every((o) => o.passed)
  const verdict = passed ? 'pass' : value === null || value === undefined ? 'no-result' : 'fail'
  return { verdict, origin: judging.origin, outcomes }
}

/** A KPI's name, as its compare row and chart are titled. */
export function kpiName(kpi: Kpi): string {
  return kpi.kind === 'conformance' ? CONFORMANCE_METRIC : kpi.key
}

/** What the KPI drill-down shows about one run's KPI. */
export interface KpiDrillDown {
  name: string
  /** `null` when the run has none. */
  value: number | null
  verdict: Verdict
  /** For an Evaluator KPI, its Evaluator result's detail items about this metric. */
  details: EvaluationResult['details']
  /** The run page tab the KPI comes from. */
  tab: 'overview' | 'evaluations' | 'conformance'
}

/**
 * One run's `kpi` in detail: its value, its verdict by `gating` (with the covering Gates'
 * reasons) and, for an Evaluator KPI, the detail items of the Evaluator result (the one of
 * `evaluations`, the run's results, with the KPI's parameters) that are about its metric.
 */
export function kpiDrillDown(
  kpi: Kpi,
  run: ConstructionRun,
  evaluations: readonly EvaluationResult[],
  gating: RunGating,
): KpiDrillDown {
  const value =
    kpi.kind === 'conformance'
      ? (run.conformance?.score ?? null)
      : kpi.kind === 'run-metric'
        ? (run.metrics[kpi.key] ?? null)
        : (evaluatorMetrics(evaluations)[kpi.key] ?? null)
  const details =
    kpi.kind !== 'evaluator'
      ? []
      : evaluations.flatMap((result) =>
          result.details.filter((d) => evaluatorMetricKey(result.evaluator, result.parameters, d.metric) === kpi.key),
        )
  return {
    name: kpiName(kpi),
    value,
    verdict: kpiVerdict(kpi, value, gating),
    details,
    tab: kpi.kind === 'conformance' ? 'conformance' : kpi.kind === 'evaluator' ? 'evaluations' : 'overview',
  }
}

/** One bound a Gate sets on a KPI: a metric Gate's `min`/`max`, a conformance Gate's `min_score`. */
export interface GateBound {
  gate: string
  bound: 'min' | 'max'
  value: number
}

/** The bounds the Gates of `outcomes` (one Gate result's or Gate Preview's) set on `kpi`, in Gate order. */
export function kpiGateBounds(kpi: Kpi, outcomes: readonly GateOutcome[]): GateBound[] {
  return outcomes
    .filter((o) => covers(o.gate, kpi))
    .flatMap(({ gate }) => {
      const limits: [GateBound['bound'], unknown][] =
        gate.check === 'conformance'
          ? [['min', gate.min_score]]
          : [
              ['min', gate.min],
              ['max', gate.max],
            ]
      return limits.flatMap(([bound, value]) => (typeof value === 'number' ? [{ gate: gate.name, bound, value }] : []))
    })
}

/** The kinds of KPI, in the order same-named charts are listed. */
const KPI_KINDS: readonly Kpi['kind'][] = ['run-metric', 'conformance', 'evaluator']

/** A run chart's series with the KPI it charts. */
export type RunChartSeries = MetricSeries & { kpi: Kpi }

/**
 * The run charts (see `runChartPoints`), each gated KPI with its Gate bounds as reference
 * lines and each point judged as the compare page judges its cell (`kpiVerdict`): pass or
 * fail, recorded over preview, with a note on where the verdicts came from. The bounds are
 * the Gate definitions the Gate Previews used. Ungated KPIs stay as they are.
 */
export function runChartSeries(
  runs: readonly ConstructionRun[],
  evaluations: readonly EvaluationResult[],
  gateResults: readonly GateResult[],
  previews: readonly GatePreview[],
): RunChartSeries[] {
  const gatings = new Map(runs.map((run) => [run.id, runGating(run.id, gateResults, previews)]))
  const definitions = previews[0]?.outcomes ?? []
  const points = runChartPoints(runs, evaluations)
  const kpiSeries = KPI_KINDS.flatMap((kind) =>
    metricSeries(points[kind]).map((series): { series: MetricSeries; kpi: Kpi } => ({
      series,
      kpi: kind === 'conformance' ? { kind } : { kind, key: series.metric },
    })),
  ).sort((a, b) => a.series.metric.localeCompare(b.series.metric))
  return kpiSeries.map(({ series, kpi }): RunChartSeries => {
    const origins: VerdictOrigin[] = []
    const points = series.points.map((point) => {
      const gating = point.id === undefined ? undefined : gatings.get(point.id)
      const verdict = gating === undefined ? undefined : kpiVerdict(kpi, point.value, gating)
      if (verdict === undefined || (verdict.verdict !== 'pass' && verdict.verdict !== 'fail')) return point
      origins.push(verdict.origin)
      return {
        ...point,
        status: {
          passed: verdict.verdict === 'pass',
          label: `${verdict.verdict} (${verdict.origin})`,
        },
      }
    })
    const references = kpiGateBounds(kpi, definitions).map((b) => ({
      name: b.gate,
      label: `${b.bound} ${formatMetric(b.value)}`,
      value: b.value,
    }))
    const note = verdictsNote(origins)
    return {
      ...series,
      kpi,
      points,
      ...(references.length > 0 ? { references } : {}),
      ...(note === undefined ? {} : { note }),
    }
  })
}

/** Where a chart's verdicts came from, e.g. "Verdicts: preview" or "Verdicts: 1 recorded, 3 preview". */
function verdictsNote(origins: readonly VerdictOrigin[]): string | undefined {
  if (origins.length === 0) return undefined
  const recorded = origins.filter((o) => o === 'recorded').length
  const preview = origins.length - recorded
  if (preview === 0) return 'Verdicts: recorded'
  if (recorded === 0) return 'Verdicts: preview'
  return `Verdicts: ${recorded} recorded, ${preview} preview`
}

/** How the compared runs fare on one KPI; `gated` counts the runs a Gate judges on it. */
export interface KpiSummary {
  pass: number
  fail: number
  noResult: number
  gated: number
}

/** The compared runs' verdicts on one KPI counted, or null when no run is gated on it. */
export function kpiSummary(verdicts: readonly Verdict[]): KpiSummary | null {
  const count = (v: Verdict['verdict']) => verdicts.filter((x) => x.verdict === v).length
  const summary = { pass: count('pass'), fail: count('fail'), noResult: count('no-result') }
  const gated = summary.pass + summary.fail + summary.noResult
  return gated === 0 ? null : { ...summary, gated }
}

/** One run's outcome of one Gate, or its overall one (`reasons` aside). */
export interface GateCell {
  passed: boolean
  origin: VerdictOrigin
  reasons: string[]
}

/**
 * The Gates section: one row per Gate (the previews' Gates in definition order, then any
 * only a recorded result has), `cells[i]` belonging to `gatings[i]` (null where its
 * judging result has no such Gate), and each run's overall verdict.
 */
export function gateRows(gatings: readonly RunGating[]): {
  gates: { name: string; cells: (GateCell | null)[] }[]
  overall: (Omit<GateCell, 'reasons'> | null)[]
} {
  const results = [...gatings.map((g) => g.preview), ...gatings.map((g) => g.recorded)]
  const names = [...new Set(results.flatMap((r) => r?.outcomes.map((o) => o.gate.name) ?? []))]
  const judging = gatings.map(judgingGateResult)
  return {
    gates: names.map((name) => ({
      name,
      cells: judging.map((j) => {
        const found = j?.result.outcomes.find((o) => o.gate.name === name)
        return j === undefined || found === undefined
          ? null
          : { passed: found.passed, origin: j.origin, reasons: found.reasons }
      }),
    })),
    overall: judging.map((j) => (j === undefined ? null : { passed: j.result.passed, origin: j.origin })),
  }
}
