import { Info } from 'lucide-react'
import { useId } from 'react'
import type { EvaluationResult } from '@/api/ontology-versions'
import { Disclosure } from '@/components/Disclosure'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { formatMetric } from '@/lib/format'
import { type EvaluatorCard as Card, evaluatorCards } from './evaluator-cards'
import { metricRows } from './evaluator-metrics'

/**
 * Evaluator results (of a version or a run) as people read them: one card per
 * Evaluator, then every metric in the raw table behind "Show all metrics".
 */
export function EvaluatorResults({ results, empty }: { results: readonly EvaluationResult[]; empty: string }) {
  if (results.length === 0) return <p className="text-sm text-muted-foreground">{empty}</p>
  return (
    <div className="space-y-3">
      <EvaluatorCards results={results} />
      <ShowAllMetrics results={results} empty={empty} />
    </div>
  )
}

/** One card per Evaluator result: a readable title, its headline metrics and a tooltip. */
export function EvaluatorCards({ results }: { results: readonly EvaluationResult[] }) {
  return (
    <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
      {evaluatorCards(results).map((card) => (
        <EvaluatorCard key={card.evaluator} card={card} />
      ))}
    </div>
  )
}

function EvaluatorCard({ card }: { card: Card }) {
  const id = useId()
  return (
    <article aria-labelledby={id} className="flex min-w-0 flex-col gap-2 rounded-lg border p-3">
      <header className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <h3 id={id} className="text-sm font-medium">
            {card.title}
          </h3>
          {card.title !== card.evaluator && (
            <code className="block truncate font-mono text-xs text-muted-foreground" title={card.evaluator}>
              {card.evaluator}
            </code>
          )}
        </div>
        {card.tooltip && (
          <Tooltip>
            <TooltipTrigger asChild>
              <button
                type="button"
                aria-label={`About ${card.title}`}
                className="rounded-sm text-muted-foreground hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
              >
                <Info aria-hidden className="size-4" />
              </button>
            </TooltipTrigger>
            <TooltipContent>{card.tooltip}</TooltipContent>
          </Tooltip>
        )}
      </header>
      <dl className="flex flex-wrap gap-x-6 gap-y-2">
        {card.headlines.map((h) => (
          <div key={h.metric}>
            <dt className="text-xs text-muted-foreground">{h.label}</dt>
            <dd className="text-xl font-semibold tabular-nums">{h.value}</dd>
          </div>
        ))}
      </dl>
      {card.useCaseVersion !== null && (
        <p className="mt-auto text-xs text-muted-foreground">Against Use Case Version {card.useCaseVersion}</p>
      )}
    </article>
  )
}

/** The raw table of every metric, folded behind "Show all metrics". */
export function ShowAllMetrics({ results, empty }: { results: readonly EvaluationResult[]; empty: string }) {
  return (
    <Disclosure label="Show all metrics">
      <EvaluatorResultTable results={results} empty={empty} />
    </Disclosure>
  )
}

/** Evaluator results (of a version or a run), one row per metric. */
export function EvaluatorResultTable({
  results,
  empty,
}: {
  results: readonly EvaluationResult[]
  empty: string
}) {
  const rows = metricRows(results)
  if (rows.length === 0) return <p className="text-sm text-muted-foreground">{empty}</p>
  return (
    <Table aria-label="Evaluator results">
      <TableHeader>
        <TableRow>
          <TableHead>Evaluator</TableHead>
          <TableHead>Metric</TableHead>
          <TableHead className="text-right">Value</TableHead>
          <TableHead className="text-right">Use Case Version</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {rows.map((row) => (
          <TableRow key={row.key}>
            <TableCell>{row.evaluator}</TableCell>
            <TableCell>{row.metric}</TableCell>
            <TableCell className="text-right tabular-nums">{formatMetric(row.value)}</TableCell>
            <TableCell className="text-right tabular-nums">
              {row.useCaseVersion ?? <span className="text-muted-foreground">—</span>}
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  )
}
