import type { StatusTone } from '@/components/status-tones'
import { formatPercent } from '@/lib/format'
import { conformanceTone } from '../runs/runs'

/** One KPI tile: a label, a value, and the tone and link it may have. */
export interface Kpi {
  label: string
  /** `—` when the KPI does not apply here. */
  value: string
  tone?: StatusTone
  /** App path the tile links to, where the value comes from. */
  to?: string
  /** One short line under the value, e.g. "of 9 Gates". */
  hint?: string
}

/** A count out of a total, e.g. Competency Questions answerable out of all of them. */
export interface Ratio {
  count: number
  total: number
}

/**
 * What an evaluation knows. Each is `null` (or absent) where it does not apply: an
 * Observation has only Drift, a Promotion only Gates.
 */
export interface EvaluationInputs {
  /** A Conformance score in [0, 1]. */
  conformance?: number | null
  /** Competency Questions answerable of all of them. */
  coverage?: Ratio | null
  /** Gates passed of all of them. */
  gates?: Ratio | null
  /** How many Drift findings. */
  drift?: number | null
}

export type EvaluationLinks = Partial<Record<keyof EvaluationInputs, string>>

export const NOT_APPLICABLE = '—'

/**
 * The four evaluation KPIs, always in this order, so a run, an Ontology Version, an
 * Observation and a Promotion read alike: Conformance, CQ coverage, Gates, Drift. One
 * that does not apply shows `—` and is not hidden.
 */
export function evaluationKpis(inputs: EvaluationInputs, links: EvaluationLinks = {}): Kpi[] {
  return [
    conformanceKpi(inputs.conformance ?? null, links.conformance),
    ratioKpi('CQ coverage', inputs.coverage ?? null, 'Competency Questions', links.coverage),
    ratioKpi('Gates', inputs.gates ?? null, 'Gates passed', links.gates),
    driftKpi(inputs.drift ?? null, links.drift),
  ]
}

export function conformanceKpi(score: number | null, to?: string): Kpi {
  if (score === null) return { label: 'Conformance', value: NOT_APPLICABLE, to }
  return { label: 'Conformance', value: formatPercent(score), tone: conformanceTone(score), to }
}

/** `2/9`: success when all, failure when none, else warning; `—` when there is nothing to count. */
export function ratioKpi(label: string, ratio: Ratio | null, of: string, to?: string): Kpi {
  if (ratio === null || ratio.total === 0) return { label, value: NOT_APPLICABLE, to }
  return { label, value: `${ratio.count}/${ratio.total}`, tone: ratioTone(ratio), hint: of, to }
}

export function driftKpi(findings: number | null, to?: string): Kpi {
  if (findings === null) return { label: 'Drift', value: NOT_APPLICABLE, to }
  return {
    label: 'Drift',
    value: String(findings),
    tone: findings === 0 ? 'success' : 'warning',
    hint: findings === 1 ? 'finding' : 'findings',
    to,
  }
}

export function ratioTone({ count, total }: Ratio): StatusTone {
  if (count === total) return 'success'
  return count === 0 ? 'failure' : 'warning'
}
