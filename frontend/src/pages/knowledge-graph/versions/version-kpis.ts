import type { GateResult } from '@/api/gate-results'
import type { ConstructionRun } from '@/api/runs'
import { matchesSearch } from '@/lib/search'
import type { Answerability } from '../use-case/answerability'
import type { EvaluationInputs } from '../evaluation/evaluation-kpis'

/**
 * An Ontology Version's evaluation KPIs: Conformance of the run that gave rise to it,
 * structural answerability, its latest Gate result; Drift is about Observations, not a
 * version, so it does not apply.
 */
export function versionEvaluationInputs(
  number: number,
  runs: readonly ConstructionRun[] | undefined,
  answerability: Answerability | undefined,
  gate: GateResult | undefined,
): EvaluationInputs {
  const run = runs?.find((r) => r.candidate_version === number)
  return {
    conformance: run?.conformance?.score ?? null,
    coverage: answerability ? { count: answerability.answerable, total: answerability.questions } : null,
    gates: gate ? { count: gate.outcomes.filter((o) => o.passed).length, total: gate.outcomes.length } : null,
    drift: null,
  }
}

/** Whether a version row matches the list search: `v3`, its origin or one of its Aliases. */
export function versionMatches(row: { number: number; origin: string; aliases: readonly string[] }, query: string): boolean {
  return matchesSearch(query, [`v${row.number}`, row.origin, ...row.aliases])
}
