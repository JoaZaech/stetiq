import { useId, type ReactNode } from 'react'
import { useQuery } from '@tanstack/react-query'
import { consumerGateResultsQuery, latestConsumerGateResult } from '@/api/consumer-gate-results'
import type { Consumer, UseCaseVersion } from '@/api/use-cases'
import { StatusLabel, type StatusTone } from '@/components/StatusLabel'
import { Skeleton } from '@/components/ui/skeleton'
import { consumerGateLine } from './consumer-gate'
import { CONSUMER_KIND_ICONS, consumerKindIcon } from './consumer-kind'
import { useLatestAnswerability, type LatestAnswerability } from './latest-answerability'
import { consumerReadiness, consumerReadinessLine } from './readiness'

interface ConsumerTilesProps {
  knowledgeGraph: string
  version: UseCaseVersion
  /** Opens the Consumer's sheet, which holds everything else. */
  onOpen: (consumer: Consumer) => void
}

/**
 * A Use Case Version's Consumers as compact tiles: each one's kind icon, name, one line of
 * description, how many of its Tasks the latest Ontology Version is ready for, and its
 * Consumer Gate's latest verdict when it declares one. A tile opens
 * the Consumer's sheet.
 */
export function ConsumerTiles({ knowledgeGraph, version, onOpen }: ConsumerTilesProps) {
  const consumers = version.use_case.consumers ?? []
  const latest = useLatestAnswerability(knowledgeGraph, version.number)
  const gated = consumers.some((c) => c.consumer_gates?.length)
  const gateResults = useQuery({ ...consumerGateResultsQuery(knowledgeGraph), enabled: gated })
  if (consumers.length === 0) {
    return (
      <p className="rounded-lg border border-dashed p-4 text-sm text-muted-foreground">
        No Consumers are declared in this Use Case Version.
      </p>
    )
  }
  return (
    <ul className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
      {consumers.map((consumer) => (
        <li key={consumer.id} className="min-w-0">
          <ConsumerTile
            consumer={consumer}
            onOpen={() => onOpen(consumer)}
            readiness={<ReadinessLine consumer={consumer} latest={latest} />}
            gate={
              gateResults.isPending ? (
                consumer.consumer_gates?.length ? <Skeleton className="h-4 w-36" /> : null
              ) : gateResults.isError ? (
                consumer.consumer_gates?.length ? (
                  <StatusLabel tone="error" label="Consumer Gate verdict not loaded" />
                ) : null
              ) : (
                <Line line={consumerGateLine(consumer, latestConsumerGateResult(gateResults.data, consumer.id))} />
              )
            }
          />
        </li>
      ))}
    </ul>
  )
}

interface ConsumerTileProps {
  consumer: Consumer
  onOpen: () => void
  readiness: ReactNode
  gate: ReactNode
}

/**
 * One Consumer's tile. Its name is the button that opens the sheet, stretched over the
 * whole tile; a control added to the tile must sit above it (`relative z-10`), as Connect
 * does, so that it opens the Connector picker and not the sheet.
 */
function ConsumerTile({ consumer, onOpen, readiness, gate }: ConsumerTileProps) {
  const titleId = useId()
  const Icon = CONSUMER_KIND_ICONS[consumerKindIcon(consumer.kind)]
  return (
    <article
      aria-labelledby={titleId}
      className="relative flex h-full min-w-0 gap-3 rounded-xl bg-card p-4 text-sm text-card-foreground ring-1 ring-foreground/10 hover:bg-muted/40 has-[h4>button:focus-visible]:ring-2 has-[h4>button:focus-visible]:ring-ring"
    >
      <span className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-muted">
        <span role="img" aria-label={consumer.kind ?? 'Consumer'} title={consumer.kind}>
          <Icon aria-hidden className="size-5 text-muted-foreground" />
        </span>
      </span>
      <div className="min-w-0 flex-1 space-y-1">
        <h4 id={titleId} className="font-semibold">
          <button
            type="button"
            onClick={onOpen}
            className="text-left after:absolute after:inset-0 after:rounded-xl focus-visible:outline-none"
          >
            {consumer.name}
          </button>
        </h4>
        {consumer.description && (
          <p className="truncate text-muted-foreground" title={consumer.description}>
            {consumer.description}
          </p>
        )}
        <div className="space-y-0.5 pt-1 text-xs">
          {readiness}
          {gate}
        </div>
      </div>
    </article>
  )
}

/** How many of the Consumer's Tasks are ready, or why that isn't known. */
function ReadinessLine({ consumer, latest }: { consumer: Consumer; latest: LatestAnswerability }) {
  if (consumer.tasks?.length) {
    // The Competency Questions list above shows the error itself.
    if (latest.state === 'pending') return <Skeleton className="h-4 w-28" />
    if (latest.state === 'error') return <StatusLabel tone="error" label="Readiness not loaded" />
  }
  return <Line line={consumerReadinessLine(consumerReadiness(consumer, judged(latest)))} />
}

const judged = (latest: LatestAnswerability) => (latest.state === 'judged' ? latest.answerability : undefined)

function Line({ line }: { line: { tone: StatusTone; label: string } | null }) {
  if (!line) return null
  return (
    <p>
      <StatusLabel tone={line.tone} label={line.label} />
    </p>
  )
}
