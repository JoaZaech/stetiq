import { latestConsumerGateResult, type ConsumerGateResult } from '@/api/consumer-gate-results'
import { latestGateResult, type GateResult } from '@/api/gate-results'
import type { DriftEvent, Observation } from '@/api/observations'
import type { ConstructionRun } from '@/api/runs'
import type { Consumer } from '@/api/use-cases'
import { RUN_STATUSES } from '@/components/run-status'
import type { StatusTone } from '@/components/status-tones'
import { formatRelativeTime } from '@/lib/format'
import type { Answerability } from '../use-case/answerability'
import { consumerGateLine } from '../use-case/consumer-gate'
import { consumerReadiness } from '../use-case/readiness'
import { gateResultSummary } from '../versions/gate-summary'

/**
 * One step of the Overview's pipeline chain: its status as a tone and a word (the icon's
 * label, e.g. "Failed"), and at most one fact under it (e.g. "6 of 9 Gates failed").
 * Missing information is `neutral`, never a pass.
 */
export interface StepStatus {
  tone: StatusTone
  status: string
  fact?: string
}

/** Upstream pipeline: the latest Construction Run's status, and how long ago it ended (or started). */
export function upstreamStatus(
  runs: readonly Pick<ConstructionRun, 'status' | 'started_at' | 'ended_at'>[],
  now: Date = new Date(),
): StepStatus {
  const latest = runs.reduce<(typeof runs)[number] | undefined>(
    (latest, run) => (latest === undefined || run.started_at >= latest.started_at ? run : latest),
    undefined,
  )
  if (!latest) return { tone: 'neutral', status: 'No runs' }
  const { tone, label } = RUN_STATUSES[latest.status]
  const fact =
    latest.ended_at === null
      ? `started ${formatRelativeTime(latest.started_at, now)}`
      : formatRelativeTime(latest.ended_at, now)
  return { tone, status: label, fact }
}

/** Gate: the newest Ontology Version's latest recorded Gate result ("v3 · 6 of 9 Gates failed"). */
export function gateStatus(newestVersion: number | undefined, results: readonly GateResult[]): StepStatus {
  if (newestVersion === undefined) return { tone: 'neutral', status: 'Not gated' }
  const latest = latestGateResult(results, 'ontology_version', String(newestVersion))
  if (!latest) return { tone: 'neutral', status: 'Not gated', fact: `v${newestVersion}` }
  return {
    tone: latest.passed ? 'success' : 'failure',
    status: latest.passed ? 'Passed' : 'Failed',
    fact: `v${newestVersion} · ${gateResultSummary(latest)}`,
  }
}

/** Where the Contract Alias points: `production → v3`, or `production (not set)`. */
export function contractAliasLabel(alias: string, version: number | undefined): string {
  return version === undefined ? `${alias} (not set)` : `${alias} → v${version}`
}

/**
 * Knowledge Graph: whether its latest Observation found Drift, with where the Contract
 * Alias points ("production → v3") and when it was observed.
 */
export function knowledgeGraphStatus(
  contract: { alias: string; version: number | undefined },
  observations: readonly Pick<Observation, 'id' | 'observed_at'>[],
  driftEvents: readonly Pick<DriftEvent, 'observation_id'>[],
  now: Date = new Date(),
): StepStatus {
  const alias = contractAliasLabel(contract.alias, contract.version)
  // Observations come oldest first.
  const latest = observations.at(-1)
  if (!latest) return { tone: 'neutral', status: 'Not observed', fact: alias }
  const fact = `${alias} · observed ${formatRelativeTime(latest.observed_at, now)}`
  return driftEvents.some((e) => e.observation_id === latest.id)
    ? { tone: 'warning', status: 'Drift', fact }
    : { tone: 'success', status: 'No Drift', fact }
}

/**
 * Consumer Gate: "1 of 3 passed" over the latest verdict of every Consumer that declares
 * one. Failed if any failed; passed only when all passed; a Consumer never evaluated
 * leaves it neutral.
 */
export function consumerGateStatus(
  consumers: readonly Consumer[],
  results: readonly ConsumerGateResult[],
): StepStatus {
  const lines = consumers.flatMap((c) => consumerGateLine(c, latestConsumerGateResult(results, c.id)) ?? [])
  if (lines.length === 0) return { tone: 'neutral', status: 'None declared' }
  const passed = lines.filter((l) => l.tone === 'success').length
  const fact = `${passed} of ${lines.length} passed`
  if (lines.some((l) => l.tone === 'failure')) return { tone: 'failure', status: 'Failed', fact }
  if (passed === lines.length) return { tone: 'success', status: 'Passed', fact }
  return { tone: 'neutral', status: 'Not evaluated yet', fact }
}

/**
 * Consumers: "2 of 3 ready", where a Consumer is ready when the latest Ontology Version
 * is ready for all its Tasks (as on its tile). A Consumer without Tasks has nothing to be
 * ready for, so it doesn't count.
 */
export function consumersStatus(
  consumers: readonly Consumer[],
  answerability: Answerability | undefined,
): StepStatus {
  if (consumers.length === 0) return { tone: 'neutral', status: 'No Consumers' }
  const readiness = consumers.map((c) => consumerReadiness(c, answerability))
  if (readiness.every((r) => r.state === 'no-tasks')) return { tone: 'neutral', status: 'No Tasks' }
  const checked = readiness.flatMap((r) => (r.state === 'checked' ? [r] : []))
  if (checked.length === 0) return { tone: 'neutral', status: 'Not checked yet' }
  const ready = checked.filter((r) => r.ready === r.tasks).length
  const fact = `${ready} of ${checked.length} ready`
  return ready === checked.length
    ? { tone: 'success', status: 'Ready', fact }
    : { tone: 'failure', status: 'Not ready', fact }
}
