import { useId } from 'react'
import { Link } from 'react-router'
import {
  type ConsumerGateResult,
  latestConsumerGateResult,
  useConsumerGateResults,
} from '@/api/consumer-gate-results'
import type { Consumer } from '@/api/use-cases'
import { kgUrl } from '@/app/knowledge-graph-sections'
import { ErrorAlert } from '@/components/ErrorAlert'
import { Planned } from '@/components/Planned'
import { StatusLabel } from '@/components/StatusLabel'
import { Skeleton } from '@/components/ui/skeleton'
import { formatDateTime, formatRelativeTime } from '@/lib/format'
import { shortRunId } from '../runs/runs'
import { consumerGateLimit, findingText } from './consumer-gate'

interface ConsumerGateSectionProps {
  knowledgeGraph: string
  /** As declared in the Use Case Version being viewed. */
  consumer: Consumer
}

/**
 * A Consumer sheet's Consumer Gate: the gates it declares in the Use Case Version being
 * viewed, and its latest recorded verdict (`stetiq consumer gate`), or one line saying it
 * declares none. The absence of a verdict reads "Not evaluated yet", never as a pass.
 */
export function ConsumerGateSection({ knowledgeGraph, consumer }: ConsumerGateSectionProps) {
  const titleId = useId()
  const gates = consumer.consumer_gates ?? []
  return (
    <section aria-labelledby={titleId} className="space-y-2">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs">
        <h3 id={titleId} className="font-medium text-muted-foreground">
          Consumer Gate
        </h3>
        <Planned
          label="Evaluated on each Observation"
          section="consumer-gate"
          tooltip="Consumer Gates will also be evaluated on each scheduled Observation, not only in the pipeline's CI."
        >
          Evaluated on each Observation
        </Planned>
      </div>
      {gates.length === 0 ? (
        <p className="text-muted-foreground">No Consumer Gate declared</p>
      ) : (
        <div className="space-y-1.5 text-xs">
          <ul aria-label="Declared Consumer Gates" className="space-y-0.5">
            {gates.map((gate) => (
              <li key={gate.name}>
                {/* A name that defaults to the check would only repeat it. */}
                {gate.name !== gate.check && <span className="font-medium">{gate.name} </span>}
                <span className="text-muted-foreground">
                  <code className="font-mono">{gate.check}</code> on Task{' '}
                  <code className="font-mono">{gate.task}</code>: {consumerGateLimit(gate.max_drop)}
                </span>
              </li>
            ))}
          </ul>
          <p className="text-muted-foreground">
            Declared in <code className="font-mono">use-case.yaml</code>; checked in CI by{' '}
            <code className="font-mono">stetiq consumer gate</code>.
          </p>
          <LatestVerdict knowledgeGraph={knowledgeGraph} consumer={consumer.id} />
        </div>
      )}
    </section>
  )
}

function LatestVerdict({ knowledgeGraph, consumer }: { knowledgeGraph: string; consumer: string }) {
  const results = useConsumerGateResults(knowledgeGraph)
  if (results.isPending) return <Skeleton className="h-4 w-40" />
  if (results.isError) return <ErrorAlert error={results.error} />
  const latest = latestConsumerGateResult(results.data, consumer)
  if (!latest) return <p className="text-muted-foreground">Not evaluated yet</p>
  return <Verdict knowledgeGraph={knowledgeGraph} result={latest} />
}

function Verdict({ knowledgeGraph, result }: { knowledgeGraph: string; result: ConsumerGateResult }) {
  const failing = result.outcomes.filter((o) => !o.passed)
  const newQuestions = result.outcomes.flatMap((o) => o.new_questions ?? [])
  return (
    <div role="group" aria-label="Latest verdict" className="space-y-1 rounded-md border p-2">
      <p className="flex flex-wrap items-center gap-x-2 gap-y-0.5">
        <StatusLabel tone={result.passed ? 'success' : 'failure'} label={result.passed ? 'Passed' : 'Failed'} />
        <span className="text-muted-foreground">
          <Link
            to={kgUrl(knowledgeGraph, 'versions', result.ontology_version)}
            className="underline-offset-4 hover:underline"
          >
            Ontology Version {result.ontology_version}
          </Link>{' '}
          · run{' '}
          <Link
            to={kgUrl(knowledgeGraph, 'runs', result.run_id)}
            className="font-mono underline-offset-4 hover:underline"
          >
            {shortRunId(result.run_id)}
          </Link>{' '}
          · <time dateTime={result.evaluated_at} title={formatDateTime(result.evaluated_at)}>
            {formatRelativeTime(result.evaluated_at)}
          </time>
        </span>
      </p>
      {failing.map((outcome) => (
        <div key={outcome.gate.name} className="space-y-0.5">
          <p>
            <span className="font-medium">{outcome.gate.name}</span> failed
          </p>
          {outcome.findings.length > 0 ? (
            <ul aria-label="Failing Competency Questions" className="space-y-0.5 pl-3">
              {outcome.findings.map((f) => (
                <li key={`${f.task}/${f.competency_question}`}>
                  <code className="font-mono">{f.task}</code> /{' '}
                  <code className="font-mono">{f.competency_question}</code>: {findingText(f)}
                </li>
              ))}
            </ul>
          ) : (
            <ul className="space-y-0.5 pl-3 text-muted-foreground">
              {outcome.reasons.map((reason) => (
                <li key={reason}>{reason}</li>
              ))}
            </ul>
          )}
        </div>
      ))}
      {newQuestions.length > 0 && (
        <ul aria-label="New Competency Questions" className="space-y-0.5 text-muted-foreground">
          {newQuestions.map((q) => (
            <li key={q}>
              <code className="font-mono">{q}</code>: new since the baseline run, not compared
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
