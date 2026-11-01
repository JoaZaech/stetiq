import { ChevronRight } from 'lucide-react'
import { Link } from 'react-router'
import { useQuery } from '@tanstack/react-query'
import { useAliases, useContractAlias } from '@/api/aliases'
import { consumerGateResultsQuery } from '@/api/consumer-gate-results'
import { useGateResults } from '@/api/gate-results'
import { useDriftEvents, useObservations } from '@/api/observations'
import { useOntologyVersions } from '@/api/ontology-versions'
import { useRuns } from '@/api/runs'
import { useUseCaseVersions } from '@/api/use-cases'
import { kgUrl } from '@/app/knowledge-graph-sections'
import { StatusLabel } from '@/components/StatusLabel'
import { Skeleton } from '@/components/ui/skeleton'
import { useLatestAnswerability } from '../use-case/latest-answerability'
import {
  consumerGateStatus,
  consumersStatus,
  gateStatus,
  knowledgeGraphStatus,
  upstreamStatus,
  type StepStatus,
} from './pipeline-status'

/**
 * Where a Knowledge Graph sits (docs/vision.md, "The two-gate pipeline"), as a status
 * chain: upstream pipeline → Gate → Knowledge Graph → Consumer Gate → Consumers. Each
 * step shows its status (`pipeline-status.ts`) and one fact, and links to its page. Each
 * step loads its own data, so one that fails doesn't hide the others. Wraps onto more
 * lines on a narrow screen.
 */
export function PipelineStrip({ name }: { name: string }) {
  const steps = [UpstreamStep, GateStep, KnowledgeGraphStep, ConsumerGateStep, ConsumersStep]
  return (
    <ol aria-label="Pipeline" className="flex min-w-0 flex-wrap items-stretch gap-y-2 text-sm">
      {steps.map((StepContent, i) => (
        // A fixed list: the index is a stable key.
        <li key={i} className="flex min-w-0 items-center">
          {i > 0 && <ChevronRight aria-hidden className="mx-1 size-4 shrink-0 text-muted-foreground" />}
          <StepContent name={name} />
        </li>
      ))}
    </ol>
  )
}

/** A step's status, or why it isn't there yet. */
type StepState = StepStatus | 'pending' | 'error'

interface QueryLike {
  isPending: boolean
  isError: boolean
}

/** `derive()` once every query has loaded. */
function stepState(queries: QueryLike[], derive: () => StepStatus): StepState {
  if (queries.some((q) => q.isError)) return 'error'
  if (queries.some((q) => q.isPending)) return 'pending'
  return derive()
}

function Step({ label, to, state }: { label: string; to: string; state: StepState }) {
  return (
    <div className="flex h-full min-w-36 flex-col gap-1 rounded-lg border px-3 py-2">
      <Link to={to} className="font-medium hover:underline">
        {label}
      </Link>
      {state === 'pending' ? (
        <Skeleton className="h-5 w-24" />
      ) : state === 'error' ? (
        <StatusLabel tone="error" label="Not loaded" />
      ) : (
        <>
          <StatusLabel tone={state.tone} label={state.status} />
          {state.fact && <p className="text-xs text-muted-foreground">{state.fact}</p>}
        </>
      )}
    </div>
  )
}

/** The latest Construction Run, linking to the runs. */
function UpstreamStep({ name }: { name: string }) {
  const runs = useRuns(name)
  const state = stepState([runs], () => upstreamStatus(runs.data!))
  return <Step label="Upstream pipeline" to={kgUrl(name, 'runs')} state={state} />
}

/** The newest Ontology Version's Gate result, linking to that version. */
function GateStep({ name }: { name: string }) {
  const versions = useOntologyVersions(name)
  const results = useGateResults(name)
  const newest = versions.data?.at(-1)?.number
  const state = stepState([versions, results], () => gateStatus(newest, results.data!))
  const to = newest === undefined ? kgUrl(name, 'versions') : kgUrl(name, 'versions', newest)
  return <Step label="Gate" to={to} state={state} />
}

/** The Contract Alias and the latest Observation, linking to the Observations. */
function KnowledgeGraphStep({ name }: { name: string }) {
  const contract = useContractAlias(name)
  const aliases = useAliases(name)
  const observations = useObservations(name)
  const driftEvents = useDriftEvents(name)
  const state = stepState([contract, aliases, observations, driftEvents], () =>
    knowledgeGraphStatus(
      { alias: contract.data!, version: aliases.data!.find((a) => a.name === contract.data)?.version },
      observations.data!,
      driftEvents.data!,
    ),
  )
  return <Step label="Knowledge Graph" to={kgUrl(name, 'observations')} state={state} />
}

/** The latest Use Case Version's Consumers, as declared. */
function useLatestConsumers(name: string) {
  const versions = useUseCaseVersions(name)
  const latest = versions.data?.at(-1)
  return { versions, latest, consumers: latest?.use_case.consumers ?? [] }
}

/** The latest Consumer Gate verdicts, linking to the Use Case's Consumer tiles. */
function ConsumerGateStep({ name }: { name: string }) {
  const { versions, consumers } = useLatestConsumers(name)
  const gated = consumers.some((c) => c.consumer_gates?.length)
  const results = useQuery({ ...consumerGateResultsQuery(name), enabled: gated })
  const state = stepState(gated ? [versions, results] : [versions], () =>
    consumerGateStatus(consumers, results.data ?? []),
  )
  return <Step label="Consumer Gate" to={kgUrl(name, 'use-case')} state={state} />
}

/** How many Consumers the latest Ontology Version is ready for, linking to the Use Case. */
function ConsumersStep({ name }: { name: string }) {
  const { versions, latest, consumers } = useLatestConsumers(name)
  const answerability = useLatestAnswerability(name, latest?.number ?? 0)
  // Only Consumers with Tasks need the answerability result.
  const needed = consumers.some((c) => c.tasks?.length)
  const judged = {
    isPending: needed && answerability.state === 'pending',
    isError: needed && answerability.state === 'error',
  }
  const state = stepState([versions, judged], () =>
    consumersStatus(consumers, answerability.state === 'judged' ? answerability.answerability : undefined),
  )
  return <Step label="Consumers" to={kgUrl(name, 'use-case')} state={state} />
}
