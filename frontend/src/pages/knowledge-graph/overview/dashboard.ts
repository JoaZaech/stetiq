import type { Alias, Promotion } from '@/api/aliases'
import { latestGateResult, type GateResult } from '@/api/gate-results'
import type { DriftEvent, Observation } from '@/api/observations'
import type { Ontology } from '@/api/ontology-versions'
import type { ConstructionRun } from '@/api/runs'
import type { Answerability } from '../use-case/answerability'
import type { Ratio } from '../evaluation/evaluation-kpis'

/**
 * What the Overview's KPI tiles and cards show, derived from data the server already
 * sends. Framework-free, so it is unit-tested; `OverviewPage` only loads and renders.
 */

/** How many recent items each Overview card lists. */
export const RECENT = 5

/** Runs newest first, by when they started; the first `n`. */
export function recentRuns<R extends Pick<ConstructionRun, 'started_at'>>(runs: readonly R[], n = RECENT): R[] {
  return [...runs].sort((a, b) => b.started_at.localeCompare(a.started_at)).slice(0, n)
}

/** The latest run's Conformance, and that run; null when no run has been assessed. */
export function latestConformance(
  runs: readonly Pick<ConstructionRun, 'id' | 'started_at' | 'conformance'>[],
): { score: number; runId: string } | null {
  const run = recentRuns(runs, runs.length).find((r) => r.conformance !== null)
  return run ? { score: run.conformance!.score, runId: run.id } : null
}

/** Competency Questions the latest Ontology Version answers, of all of them. */
export function coverageRatio(answerability: Answerability | undefined): Ratio | null {
  return answerability ? { count: answerability.answerable, total: answerability.questions } : null
}

/** The newest version's latest recorded Gate result as Gates passed of all; null when never gated. */
export function gatesRatio(newestVersion: number | undefined, results: readonly GateResult[]): Ratio | null {
  if (newestVersion === undefined) return null
  const latest = latestGateResult(results, 'ontology_version', String(newestVersion))
  if (!latest) return null
  return { count: latest.outcomes.filter((o) => o.passed).length, total: latest.outcomes.length }
}

/** How many Drift findings the latest Observation has: 0 without Drift, null when never observed. */
export function latestDriftFindings(
  observations: readonly Pick<Observation, 'id'>[],
  driftEvents: readonly Pick<DriftEvent, 'observation_id' | 'findings'>[],
): number | null {
  // Observations come oldest first.
  const latest = observations.at(-1)
  if (!latest) return null
  return driftEvents.find((e) => e.observation_id === latest.id)?.findings.length ?? 0
}

/** An Observation with how many Drift findings it had (0: no Drift). */
export interface ObservationSummary {
  observation: Observation
  findings: number
}

/** The latest Observations, newest first, each with its Drift findings. */
export function recentObservations(
  observations: readonly Observation[],
  driftEvents: readonly Pick<DriftEvent, 'observation_id' | 'findings'>[],
  n = RECENT,
): ObservationSummary[] {
  const findings = new Map(driftEvents.map((e) => [e.observation_id, e.findings.length]))
  return [...observations]
    .reverse()
    .slice(0, n)
    .map((observation) => ({ observation, findings: findings.get(observation.id) ?? 0 }))
}

/** The latest Promotions, newest first. */
export function recentPromotions(promotions: readonly Promotion[], n = RECENT): Promotion[] {
  return [...promotions].sort((a, b) => b.promoted_at.localeCompare(a.promoted_at)).slice(0, n)
}

/** How big an Ontology is: its Classes, Relations, Attributes (on both) and patterns. */
export function ontologySize(ontology: Ontology): { classes: number; relations: number; attributes: number; patterns: number } {
  const attributes = [...ontology.node_types, ...ontology.relationship_types].reduce(
    (sum, concept) => sum + (concept.properties?.length ?? 0),
    0,
  )
  return {
    classes: ontology.node_types.length,
    relations: ontology.relationship_types.length,
    attributes,
    patterns: ontology.patterns.length,
  }
}

/** The names of the Aliases pointing to `version`, sorted. */
export function aliasesOf(aliases: readonly Pick<Alias, 'name' | 'version'>[], version: number): string[] {
  return aliases
    .filter((a) => a.version === version)
    .map((a) => a.name)
    .sort()
}

/**
 * A description split into its first sentence, for the Overview's one-line About, and the
 * rest, shown behind "More" (empty when there is none).
 */
export function descriptionSummary(description: string | null | undefined): { summary: string; rest: string } | null {
  const text = description?.trim()
  if (!text) return null
  const firstParagraph = text.split(/\n\s*\n/)[0]
  const head = firstParagraph.match(/^[\s\S]+?[.!?](?=\s|$)/)?.[0] ?? firstParagraph
  return { summary: head.replace(/\s*\n\s*/g, ' '), rest: text.slice(head.length).trim() }
}
