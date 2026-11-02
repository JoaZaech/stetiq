import { useState, type ReactNode } from 'react'
import { ArrowRight, Check, ChevronRight, Copy } from 'lucide-react'
import { Link } from 'react-router'
import { useQuery } from '@tanstack/react-query'
import { useAliases, useContractAlias } from '@/api/aliases'
import { consumerGateResultsQuery } from '@/api/consumer-gate-results'
import { latestGateResult, useGateResults } from '@/api/gate-results'
import { useDriftEvents, useObservations } from '@/api/observations'
import { useOntologyVersions } from '@/api/ontology-versions'
import { useRuns } from '@/api/runs'
import { useUseCaseVersions } from '@/api/use-cases'
import { kgUrl } from '@/app/knowledge-graph-sections'
import { STATUS_TONES, type StatusTone } from '@/components/status-tones'
import { StatusLabel } from '@/components/StatusLabel'
import { Skeleton } from '@/components/ui/skeleton'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { formatPercent } from '@/lib/format'
import { cn } from '@/lib/utils'
import { ratioTone, type Ratio } from '../evaluation/evaluation-kpis'
import { conformanceTone } from '../runs/runs'
import { useLatestAnswerability } from '../use-case/latest-answerability'
import { coverageRatio, gatesRatio, latestConformance, latestDriftFindings, recentRuns } from './dashboard'
import {
  consumerGateNext,
  consumersNext,
  gateNext,
  knowledgeGraphNext,
  upstreamNext,
  type NextStep,
} from './pipeline-next'
import {
  consumerGateStatus,
  consumersStatus,
  gateStatus,
  knowledgeGraphStatus,
  upstreamStatus,
  type StepStatus,
} from './pipeline-status'

/**
 * Where a Knowledge Graph sits (docs/vision.md, "The two-gate pipeline") and the
 * Overview's KPIs in one row: upstream pipeline → Gate → Knowledge Graph → Consumer Gate
 * → Consumers. Each stage shows its status (`pipeline-status.ts`, its fact on hover), its
 * numbers, and, when it isn't green, one line with the next step: a page to open or a
 * command to copy (`pipeline-next.ts`). Each stage loads its own data, so one that fails doesn't hide the
 * others. Five equal columns on a wide screen, two, then one, on narrower ones.
 */
export function PipelineStrip({ name }: { name: string }) {
  const stages = [UpstreamStage, GateStage, KnowledgeGraphStage, ConsumerGateStage, ConsumersStage]
  return (
    <ol
      aria-label="Pipeline"
      className="grid min-w-0 grid-cols-1 overflow-hidden rounded-lg border bg-card text-sm sm:grid-cols-2 lg:grid-cols-5"
    >
      {stages.map((StageContent, i) => (
        // A fixed list: the index is a stable key.
        <li
          key={i}
          className={cn(
            'relative flex min-w-0 flex-col border-t first:border-t-0 sm:[&:nth-child(2)]:border-t-0 lg:border-t-0',
            i > 0 && 'lg:border-l',
            i % 2 === 1 && 'sm:border-l',
          )}
        >
          <StageContent name={name} />
          {i < stages.length - 1 && (
            <span
              aria-hidden
              className="absolute top-1/2 -right-2.5 z-10 hidden size-5 -translate-y-1/2 items-center justify-center rounded-full border bg-background text-muted-foreground lg:flex"
            >
              <ChevronRight className="size-3" />
            </span>
          )}
        </li>
      ))}
    </ol>
  )
}

/** A stage's status, or why it isn't there yet. */
type StageState = StepStatus | 'pending' | 'error'

interface QueryLike {
  isPending: boolean
  isError: boolean
}

/** A stage whose metric already says what its fact does ("2/2" and "2 of 2 passed") shows only the metric. */
const withoutFact = (state: StageState): StageState => (typeof state === 'object' ? { ...state, fact: undefined } : state)

/** `derive()` once every query has loaded. */
function stageState(queries: QueryLike[], derive: () => StepStatus): StageState {
  if (queries.some((q) => q.isError)) return 'error'
  if (queries.some((q) => q.isPending)) return 'pending'
  return derive()
}

/** One number of a stage: `100% Conformance`, `2/9 Gates passed`; `—` when there is none. */
interface Metric {
  label: string
  value: string
  tone?: StatusTone
}

const ratioMetric = (label: string, ratio: Ratio | null | undefined): Metric =>
  ratio && ratio.total > 0
    ? { label, value: `${ratio.count}/${ratio.total}`, tone: ratioTone(ratio) }
    : { label, value: '—' }

function Stage({
  step,
  label,
  to,
  state,
  metrics = [],
  next,
}: {
  step: number
  label: string
  to: string
  state: StageState
  metrics?: Metric[]
  next?: NextStep
}) {
  return (
    <div className="flex h-full min-w-0 flex-col gap-2 px-4 py-3">
      <Link to={to} className="group flex items-center gap-1.5 text-xs font-medium text-muted-foreground hover:text-foreground">
        <span aria-hidden className="tabular-nums">{step}</span>
        <span className="truncate group-hover:underline">{label}</span>
      </Link>
      {state === 'pending' ? (
        <Skeleton className="h-16 w-full" />
      ) : state === 'error' ? (
        <StatusLabel tone="error" label="Not loaded" />
      ) : (
        <>
          <StageStatus status={state} />
          {metrics.length > 0 && (
            <dl className="flex flex-wrap gap-x-4 gap-y-1">
              {metrics.map((m) => (
                // The label is the `dt`, so it comes first; the value shows above it.
                <div key={m.label} className="flex min-w-0 flex-col-reverse">
                  <dt className="text-xs text-muted-foreground">{m.label}</dt>
                  <dd
                    className={cn(
                      'text-lg leading-tight font-semibold tabular-nums',
                      m.tone ? STATUS_TONES[m.tone].className : 'text-muted-foreground',
                    )}
                  >
                    {m.value}
                  </dd>
                </div>
              ))}
            </dl>
          )}
          {next && (
            <div className="mt-auto pt-1">
              <Next next={next} />
            </div>
          )}
        </>
      )}
    </div>
  )
}

/**
 * A stage's status. Its fact (when the latest run ended, the Contract Alias and when it was
 * observed) shows on hover or focus, not as a line of its own: the cards below repeat it.
 */
function StageStatus({ status }: { status: StepStatus }) {
  const label = (
    <span className="font-medium">
      <StatusLabel tone={status.tone} label={status.status} />
    </span>
  )
  if (!status.fact) return label
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <span tabIndex={0} aria-description={status.fact} className="w-fit rounded-sm outline-none focus-visible:ring-2 focus-visible:ring-ring">
          {label}
        </span>
      </TooltipTrigger>
      <TooltipContent>{status.fact}</TooltipContent>
    </Tooltip>
  )
}

/** A link with an arrow, or a one-line action that copies a command, shown on hover. */
function Next({ next }: { next: NextStep }): ReactNode {
  if (next.kind === 'link') {
    return (
      <Link to={next.to} className="inline-flex items-center gap-1 text-xs text-primary underline-offset-4 hover:underline">
        {next.label}
        <ArrowRight aria-hidden className="size-3" />
      </Link>
    )
  }
  return <CopyCommand label={next.label} command={next.command} />
}

/** `⧉ Evaluate its Gates`: copies the command; the command itself is in the tooltip. */
function CopyCommand({ label, command }: { label: string; command: string }) {
  const [copied, setCopied] = useState(false)
  async function copy() {
    await navigator.clipboard.writeText(command)
    setCopied(true)
    setTimeout(() => setCopied(false), 1500)
  }
  const Icon = copied ? Check : Copy
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <button
          type="button"
          aria-label={`${label}: copy “${command}”`}
          onClick={() => void copy()}
          className="inline-flex max-w-full items-center gap-1 rounded-sm text-left text-xs text-primary underline-offset-4 outline-none hover:underline focus-visible:ring-2 focus-visible:ring-ring"
        >
          <Icon aria-hidden className="size-3 shrink-0" />
          <span className="truncate">{copied ? 'Copied' : label}</span>
        </button>
      </TooltipTrigger>
      <TooltipContent className="max-w-none">
        <code className="font-mono whitespace-nowrap">{command}</code>
      </TooltipContent>
    </Tooltip>
  )
}

/** The latest Construction Run and the latest Conformance, linking to the runs. */
function UpstreamStage({ name }: { name: string }) {
  const runs = useRuns(name)
  const state = stageState([runs], () => upstreamStatus(runs.data!))
  const latest = runs.data && recentRuns(runs.data, 1)[0]
  const conformance = runs.data ? latestConformance(runs.data) : null
  const metrics: Metric[] = [
    conformance
      ? { label: 'Conformance', value: formatPercent(conformance.score), tone: conformanceTone(conformance.score) }
      : { label: 'Conformance', value: '—' },
  ]
  return (
    <Stage
      step={1}
      label="Upstream pipeline"
      to={kgUrl(name, 'runs')}
      state={state}
      metrics={metrics}
      next={runs.data ? upstreamNext(name, latest) : undefined}
    />
  )
}

/** The newest Ontology Version's Gate result, linking to that version. */
function GateStage({ name }: { name: string }) {
  const versions = useOntologyVersions(name)
  const results = useGateResults(name)
  const newest = versions.data?.at(-1)?.number
  const state = stageState([versions, results], () => gateStatus(newest, results.data!))
  const to = newest === undefined ? kgUrl(name, 'versions') : kgUrl(name, 'versions', newest)
  const latest = newest === undefined || !results.data ? undefined : latestGateResult(results.data, 'ontology_version', String(newest))
  const verdict = latest === undefined ? 'none' : latest.passed ? 'passed' : 'failed'
  return (
    <Stage
      step={2}
      label="Gate"
      to={to}
      state={state}
      metrics={[ratioMetric('Gates passed', results.data ? gatesRatio(newest, results.data) : null)]}
      next={results.data ? gateNext(name, newest, verdict) : undefined}
    />
  )
}

/** The Contract Alias and the latest Observation's Drift, linking to the Observations. */
function KnowledgeGraphStage({ name }: { name: string }) {
  const contract = useContractAlias(name)
  const aliases = useAliases(name)
  const observations = useObservations(name)
  const driftEvents = useDriftEvents(name)
  const state = stageState([contract, aliases, observations, driftEvents], () =>
    knowledgeGraphStatus(
      { alias: contract.data!, version: aliases.data!.find((a) => a.name === contract.data)?.version },
      observations.data!,
      driftEvents.data!,
    ),
  )
  const findings = observations.data && driftEvents.data ? latestDriftFindings(observations.data, driftEvents.data) : null
  const metrics: Metric[] = [
    findings === null
      ? { label: 'Drift findings', value: '—' }
      : { label: 'Drift findings', value: String(findings), tone: findings === 0 ? 'success' : 'warning' },
  ]
  return (
    <Stage
      step={3}
      label="Knowledge Graph"
      to={kgUrl(name, 'observations')}
      state={state}
      metrics={metrics}
      next={observations.data ? knowledgeGraphNext(name, observations.data.at(-1)?.id, findings) : undefined}
    />
  )
}

/** The latest Use Case Version's Consumers, as declared. */
function useLatestConsumers(name: string) {
  const versions = useUseCaseVersions(name)
  const latest = versions.data?.at(-1)
  return { versions, latest, consumers: latest?.use_case.consumers ?? [] }
}

/** The latest Consumer Gate verdicts, linking to the Use Case's Consumers. */
function ConsumerGateStage({ name }: { name: string }) {
  const { versions, consumers } = useLatestConsumers(name)
  const gated = consumers.some((c) => c.consumer_gates?.length)
  const results = useQuery({ ...consumerGateResultsQuery(name), enabled: gated })
  const state = stageState(gated ? [versions, results] : [versions], () =>
    consumerGateStatus(consumers, results.data ?? []),
  )
  const status = typeof state === 'object' ? state : undefined
  return (
    <Stage
      step={4}
      label="Consumer Gate"
      to={`${kgUrl(name, 'use-case')}?tab=consumers`}
      state={withoutFact(state)}
      metrics={[ratioMetric('Consumer Gates passed', status?.ratio)]}
      next={status ? consumerGateNext(name, status.status) : undefined}
    />
  )
}

/**
 * How many Consumers the latest Ontology Version is ready for, and how many Competency
 * Questions it answers, linking to the Use Case.
 */
function ConsumersStage({ name }: { name: string }) {
  const { versions, latest, consumers } = useLatestConsumers(name)
  const answerability = useLatestAnswerability(name, latest?.number ?? 0)
  // Only Consumers with Tasks need the answerability result.
  const needed = consumers.some((c) => c.tasks?.length)
  const judged = {
    isPending: needed && answerability.state === 'pending',
    isError: needed && answerability.state === 'error',
  }
  const result = answerability.state === 'judged' ? answerability.answerability : undefined
  const state = stageState([versions, judged], () => consumersStatus(consumers, result))
  const status = typeof state === 'object' ? state : undefined
  return (
    <Stage
      step={5}
      label="Consumers"
      to={kgUrl(name, 'use-case')}
      state={withoutFact(state)}
      metrics={[ratioMetric('ready', status?.ratio), ratioMetric('CQs answerable', coverageRatio(result))]}
      next={consumersNext(name, result)}
    />
  )
}
