import type { ConstructionRun } from '@/api/runs'
import { kgUrl } from '@/app/knowledge-graph-sections'
import type { Answerability } from '../use-case/answerability'
import { shortRunId } from '../runs/runs'

/**
 * What a pipeline step asks of the user next, when it isn't green: a page to open, or a
 * CLI command to run (shown with a copy button). A green step has none.
 */
export type NextStep = { kind: 'link'; label: string; to: string } | { kind: 'command'; label: string; command: string }

/** Upstream pipeline: track a first run, or open the latest one that failed. */
export function upstreamNext(
  name: string,
  latest: Pick<ConstructionRun, 'id' | 'status'> | undefined,
): NextStep | undefined {
  if (!latest) return { kind: 'command', label: 'Track a run', command: 'stetiq run' }
  if (latest.status === 'failed') {
    return { kind: 'link', label: `Why run ${shortRunId(latest.id)} failed`, to: kgUrl(name, 'runs', latest.id, 'evaluation') }
  }
  return undefined
}

/** Gate: evaluate the newest version's Gates, or open the ones that failed. */
export function gateNext(
  name: string,
  newestVersion: number | undefined,
  verdict: 'passed' | 'failed' | 'none',
): NextStep | undefined {
  if (newestVersion === undefined) return undefined
  if (verdict === 'none') {
    return { kind: 'command', label: 'Evaluate its Gates', command: `stetiq gate ${name} --version ${newestVersion}` }
  }
  if (verdict === 'failed') return { kind: 'link', label: 'See the failed Gates', to: kgUrl(name, 'versions', newestVersion) }
  return undefined
}

/** Knowledge Graph: take a first Observation, or review the latest one's Drift findings. */
export function knowledgeGraphNext(
  name: string,
  latestObservationId: string | undefined,
  findings: number | null,
): NextStep | undefined {
  if (latestObservationId === undefined) {
    return { kind: 'command', label: 'Take an Observation', command: `stetiq observe ${name}` }
  }
  if (findings) {
    const sheet = new URLSearchParams({ sheet: `observation:${latestObservationId}` })
    return {
      kind: 'link',
      label: `Review ${findings} Drift ${findings === 1 ? 'finding' : 'findings'}`,
      to: `${kgUrl(name, 'observations')}?${sheet}`,
    }
  }
  return undefined
}

/** Consumer Gate, by the step's status word: declare one, open the failing Consumers, or evaluate them. */
export function consumerGateNext(name: string, status: string): NextStep | undefined {
  const consumers = `${kgUrl(name, 'use-case')}?tab=consumers`
  switch (status) {
    case 'None declared':
      return { kind: 'link', label: 'Declare one on a Consumer', to: consumers }
    case 'Failed':
      return { kind: 'link', label: 'See the failing Consumers', to: consumers }
    case 'Not evaluated yet':
      return { kind: 'command', label: 'Evaluate them', command: `stetiq consumer gate ${name}` }
    default:
      return undefined
  }
}

/** Consumers: the Competency Questions holding them back, in the question catalog, filtered. */
export function consumersNext(name: string, answerability: Answerability | undefined): NextStep | undefined {
  if (!answerability) return undefined
  const count = (status: 'unanswerable' | 'unmapped') => answerability.rows.filter((r) => r.status === status).length
  const unanswerable = count('unanswerable')
  if (unanswerable > 0) {
    return {
      kind: 'link',
      label: `${unanswerable} ${unanswerable === 1 ? 'question' : 'questions'} unanswerable`,
      to: `${kgUrl(name, 'use-case')}?status=unanswerable`,
    }
  }
  const unmapped = count('unmapped')
  if (unmapped > 0) {
    return {
      kind: 'link',
      label: `${unmapped} ${unmapped === 1 ? 'question' : 'questions'} can't be checked`,
      to: `${kgUrl(name, 'use-case')}?status=unmapped`,
    }
  }
  return undefined
}
