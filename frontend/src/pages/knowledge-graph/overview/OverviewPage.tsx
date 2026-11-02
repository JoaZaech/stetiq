import { useId, useState, type ReactNode } from 'react'
import { ArrowRight } from 'lucide-react'
import { Link } from 'react-router'
import { useAliases, useContractAlias, usePromotions } from '@/api/aliases'
import { useGateResults } from '@/api/gate-results'
import { useEvolutionMode, useKnowledgeGraph } from '@/api/knowledge-graph'
import { useDriftEvents, useObservations } from '@/api/observations'
import { useOntologyVersions } from '@/api/ontology-versions'
import { useRuns } from '@/api/runs'
import { useUseCaseVersions } from '@/api/use-cases'
import { kgUrl } from '@/app/knowledge-graph-sections'
import { Disclosure } from '@/components/Disclosure'
import { KpiTiles, type KpiTile } from '@/components/KpiTiles'
import { Markdown } from '@/components/Markdown'
import { PageHeader } from '@/components/PageHeader'
import { RunStatusLabel } from '@/components/RunStatusLabel'
import { STATUS_TONES } from '@/components/status-tones'
import { StatusLabel } from '@/components/StatusLabel'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import { formatPercent, formatRelativeTime } from '@/lib/format'
import { conformanceKpi, driftKpi, ratioKpi } from '../evaluation/evaluation-kpis'
import { EditDescription } from '../KnowledgeGraphHeader'
import { useKnowledgeGraphName } from '../params'
import { conformanceTone, shortRunId } from '../runs/runs'
import { useLatestAnswerability } from '../use-case/latest-answerability'
import {
  aliasesOf,
  consumersRatio,
  coverageRatio,
  descriptionSummary,
  gatesRatio,
  latestConformance,
  latestDriftFindings,
  ontologySize,
  recentObservations,
  recentPromotions,
  recentRuns,
} from './dashboard'
import { PipelineStrip } from './PipelineStrip'

/**
 * `/kg/:name/overview`, where a Knowledge Graph opens: a dashboard of everything in one
 * place. A one-line About, the pipeline strip as a status chain, five KPI tiles, then the
 * recent runs, Observations, the current Ontology Version and the Promotions, each linking
 * to its page. Every part loads its own data, so one that fails doesn't hide the others.
 */
export function OverviewPage() {
  const name = useKnowledgeGraphName()
  return (
    <>
      <PageHeader title={name} />
      <div className="space-y-6">
        <About name={name} />
        <PipelineStrip name={name} />
        <OverviewKpis name={name} />
        <div className="grid gap-4 lg:grid-cols-2">
          <RecentRunsCard name={name} />
          <RecentObservationsCard name={name} />
          <OntologyVersionCard name={name} />
          <PromotionsCard name={name} />
        </div>
      </div>
    </>
  )
}

/** The description's first sentence, the rest behind "More", and the Evolution Mode. */
function About({ name }: { name: string }) {
  const id = useId()
  const description = useKnowledgeGraph(name).data?.description
  const summary = descriptionSummary(description)
  return (
    <section aria-labelledby={id} className="space-y-1">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
        <h2 id={id} className="text-sm font-semibold">
          About
        </h2>
        <dl className="flex items-center gap-1.5 text-xs">
          <dt className="text-muted-foreground">Evolution Mode</dt>
          <dd>
            <EvolutionModeValue name={name} />
          </dd>
        </dl>
        <div className="ml-auto">
          <EditDescription name={name} />
        </div>
      </div>
      <div className="text-sm text-muted-foreground">
        {summary === null ? (
          <p className="italic">No description</p>
        ) : (
          <div className="flex flex-wrap items-baseline gap-x-2">
            <Markdown>{summary.summary}</Markdown>
            {summary.rest && (
              <Disclosure label="More" className="basis-full">
                <Markdown>{summary.rest}</Markdown>
              </Disclosure>
            )}
          </div>
        )}
      </div>
    </section>
  )
}

function EvolutionModeValue({ name }: { name: string }) {
  const mode = useEvolutionMode(name)
  if (mode.isPending) return <Skeleton className="h-5 w-16" />
  if (mode.isError) return <span className="text-destructive">unavailable</span>
  return <Badge variant="outline">{mode.data}</Badge>
}

interface QueryLike {
  isPending: boolean
  isError: boolean
}

/** A tile while its data loads (`…`) or when it failed to (`Not loaded`), else `build()`. */
function tile(label: string, to: string, queries: QueryLike[], build: () => KpiTile): KpiTile {
  if (queries.some((q) => q.isError)) return { label, value: 'Not loaded', tone: 'error', to }
  if (queries.some((q) => q.isPending)) return { label, value: '…', to }
  return build()
}

/** CQ coverage, Conformance, Gates, Drift and Consumers, each linking to where it comes from. */
function OverviewKpis({ name }: { name: string }) {
  const runs = useRuns(name)
  const versions = useOntologyVersions(name)
  const gateResults = useGateResults(name)
  const observations = useObservations(name)
  const driftEvents = useDriftEvents(name)
  const useCases = useUseCaseVersions(name)
  const latestUseCase = useCases.data?.at(-1)
  const answerability = useLatestAnswerability(name, latestUseCase?.number ?? 0)
  const judged = answerability.state === 'judged' ? answerability.answerability : undefined
  const answerabilityQuery = {
    isPending: answerability.state === 'pending',
    isError: answerability.state === 'error',
  }
  const newest = versions.data?.at(-1)?.number
  const useCaseUrl = kgUrl(name, 'use-case')

  const tiles = [
    tile('CQ coverage', useCaseUrl, [useCases, answerabilityQuery], () =>
      ratioKpi('CQ coverage', coverageRatio(judged), 'Competency Questions answerable', useCaseUrl),
    ),
    tile('Conformance', kgUrl(name, 'runs'), [runs], () => {
      const latest = latestConformance(runs.data!)
      return {
        ...conformanceKpi(latest?.score ?? null, latest ? kgUrl(name, 'runs', latest.runId) : kgUrl(name, 'runs')),
        hint: latest ? `run ${shortRunId(latest.runId)}` : undefined,
      }
    }),
    tile('Gates', kgUrl(name, 'versions'), [versions, gateResults], () =>
      ratioKpi(
        'Gates',
        gatesRatio(newest, gateResults.data!),
        `Gates passed by v${newest}`,
        newest === undefined ? kgUrl(name, 'versions') : kgUrl(name, 'versions', newest),
      ),
    ),
    tile('Drift', kgUrl(name, 'observations'), [observations, driftEvents], () =>
      driftKpi(latestDriftFindings(observations.data!, driftEvents.data!), kgUrl(name, 'observations')),
    ),
    tile('Consumers', useCaseUrl, [useCases, answerabilityQuery], () =>
      ratioKpi('Consumers', consumersRatio(latestUseCase?.use_case.consumers ?? [], judged), 'ready', useCaseUrl),
    ),
  ]
  return <KpiTiles tiles={tiles} className="sm:grid-cols-3 lg:grid-cols-5" />
}

/** A dashboard card: a title, a link to the whole list, and its rows. */
function Card({ title, to, linkLabel, children }: { title: string; to: string; linkLabel: string; children: ReactNode }) {
  const id = useId()
  return (
    <section aria-labelledby={id} className="min-w-0 rounded-lg border">
      <div className="flex items-center justify-between gap-2 border-b px-3 py-2">
        <h2 id={id} className="text-sm font-semibold">
          {title}
        </h2>
        <Link to={to} className="inline-flex items-center gap-1 text-xs text-primary underline-offset-4 hover:underline">
          {linkLabel}
          <ArrowRight aria-hidden className="size-3" />
        </Link>
      </div>
      <div className="px-3 py-2 text-sm">{children}</div>
    </section>
  )
}

/** A card's body while its data loads, after it failed to, or with nothing in it. */
function CardState({ queries, empty, isEmpty, children }: { queries: (QueryLike & { error: Error | null })[]; empty: string; isEmpty: () => boolean; children: () => ReactNode }) {
  const failed = queries.find((q) => q.isError)
  if (failed) return <StatusLabel tone="error" label={failed.error?.message ?? 'Not loaded'} />
  if (queries.some((q) => q.isPending)) return <Skeleton className="h-24 w-full" />
  if (isEmpty()) return <p className="py-1 text-muted-foreground">{empty}</p>
  return <>{children()}</>
}

/** Rows of a card: each a grid line of a few cells. */
function Rows({ label, children }: { label: string; children: ReactNode }) {
  return (
    <ul aria-label={label} className="divide-y">
      {children}
    </ul>
  )
}

const rowClass = 'flex flex-wrap items-center gap-x-3 gap-y-0.5 py-1.5'

function Ago({ iso, now }: { iso: string; now: Date }) {
  return (
    <time dateTime={iso} className="ml-auto text-xs text-muted-foreground">
      {formatRelativeTime(iso, now)}
    </time>
  )
}

function RecentRunsCard({ name }: { name: string }) {
  const runs = useRuns(name)
  const [now] = useState(() => new Date())
  return (
    <Card title="Recent runs" to={kgUrl(name, 'runs')} linkLabel="All runs">
      <CardState queries={[runs]} empty="No Construction Runs yet." isEmpty={() => runs.data!.length === 0}>
        {() => (
          <Rows label="Recent runs">
            {recentRuns(runs.data!).map((run) => (
              <li key={run.id} className={rowClass}>
                <Link
                  to={kgUrl(name, 'runs', run.id)}
                  className="font-mono text-xs text-primary underline-offset-4 hover:underline"
                >
                  {shortRunId(run.id)}
                </Link>
                <RunStatusLabel status={run.status} />
                {run.conformance && (
                  <span
                    className={`tabular-nums ${STATUS_TONES[conformanceTone(run.conformance.score)].className}`}
                    title="Conformance"
                  >
                    {formatPercent(run.conformance.score)}
                  </span>
                )}
                <Ago iso={run.started_at} now={now} />
              </li>
            ))}
          </Rows>
        )}
      </CardState>
    </Card>
  )
}

function RecentObservationsCard({ name }: { name: string }) {
  const observations = useObservations(name)
  const driftEvents = useDriftEvents(name)
  const [now] = useState(() => new Date())
  return (
    <Card title="Latest Observations" to={kgUrl(name, 'observations')} linkLabel="All Observations">
      <CardState
        queries={[observations, driftEvents]}
        empty="Not observed yet."
        isEmpty={() => observations.data!.length === 0}
      >
        {() => (
          <Rows label="Latest Observations">
            {recentObservations(observations.data!, driftEvents.data!).map(({ observation, findings }) => (
              <li key={observation.id} className={rowClass}>
                <StatusLabel
                  tone={findings > 0 ? 'warning' : 'success'}
                  label={findings > 0 ? `Drift · ${findings}` : 'No Drift'}
                />
                {observation.run_id ? (
                  <Link
                    to={kgUrl(name, 'runs', observation.run_id)}
                    className="font-mono text-xs text-primary underline-offset-4 hover:underline"
                  >
                    {shortRunId(observation.run_id)}
                  </Link>
                ) : (
                  <span className="text-xs text-muted-foreground">on demand</span>
                )}
                <Ago iso={observation.observed_at} now={now} />
              </li>
            ))}
          </Rows>
        )}
      </CardState>
    </Card>
  )
}

/** The version the Contract Alias points to (else the newest), its Aliases and its size. */
function OntologyVersionCard({ name }: { name: string }) {
  const versions = useOntologyVersions(name)
  const aliases = useAliases(name)
  const contract = useContractAlias(name)
  return (
    <Card title="Current Ontology Version" to={kgUrl(name, 'versions')} linkLabel="All versions">
      <CardState
        queries={[versions, aliases, contract]}
        empty="No Ontology Version yet."
        isEmpty={() => versions.data!.length === 0}
      >
        {() => {
          const contractVersion = aliases.data!.find((a) => a.name === contract.data)?.version
          const newest = versions.data!.at(-1)!
          const current = versions.data!.find((v) => v.number === contractVersion) ?? newest
          const size = ontologySize(current.ontology)
          const pointing = aliasesOf(aliases.data!, current.number)
          return (
            <div className="space-y-2 py-1">
              <div className="flex flex-wrap items-center gap-2">
                <Link
                  to={kgUrl(name, 'versions', current.number)}
                  className="text-base font-semibold text-primary underline-offset-4 hover:underline"
                >
                  v{current.number}
                </Link>
                {pointing.map((alias) => (
                  <Badge key={alias} variant="outline">
                    {alias}
                  </Badge>
                ))}
                {newest.number !== current.number && (
                  <Link
                    to={kgUrl(name, 'versions', newest.number)}
                    className="ml-auto text-xs text-muted-foreground underline-offset-4 hover:underline"
                  >
                    Newest v{newest.number}
                  </Link>
                )}
              </div>
              <dl aria-label="Size" className="grid grid-cols-4 gap-2">
                {(
                  [
                    ['Classes', size.classes],
                    ['Relations', size.relations],
                    ['Attributes', size.attributes],
                    ['Patterns', size.patterns],
                  ] as const
                ).map(([label, count]) => (
                  <div key={label} className="min-w-0">
                    <dt className="truncate text-xs text-muted-foreground">{label}</dt>
                    <dd className="font-semibold tabular-nums">{count}</dd>
                  </div>
                ))}
              </dl>
            </div>
          )
        }}
      </CardState>
    </Card>
  )
}

const PROMOTION_GATE = {
  passed: { tone: 'success', label: 'Passed' },
  failed: { tone: 'failure', label: 'Failed' },
} as const

function PromotionsCard({ name }: { name: string }) {
  const promotions = usePromotions(name)
  const [now] = useState(() => new Date())
  return (
    <Card title="Recent Promotions" to={kgUrl(name, 'promotions')} linkLabel="All Promotions">
      <CardState queries={[promotions]} empty="No Promotions yet." isEmpty={() => promotions.data!.length === 0}>
        {() => (
          <Rows label="Recent Promotions">
            {recentPromotions(promotions.data!).map((p) => (
              <li key={`${p.alias}/${p.promoted_at}`} className={rowClass}>
                <span className="font-medium">{p.alias}</span>
                <span className="tabular-nums">
                  {p.from_version === null ? '' : `v${p.from_version} → `}
                  <Link
                    to={kgUrl(name, 'versions', p.to_version)}
                    className="text-primary underline-offset-4 hover:underline"
                  >
                    v{p.to_version}
                  </Link>
                </span>
                {p.gate_result === null ? (
                  <StatusLabel tone="neutral" label="Not gated" />
                ) : (
                  <StatusLabel {...PROMOTION_GATE[p.gate_result]} />
                )}
                <Ago iso={p.promoted_at} now={now} />
              </li>
            ))}
          </Rows>
        )}
      </CardState>
    </Card>
  )
}
