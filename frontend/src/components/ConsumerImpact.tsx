import { type ReactNode, useId } from 'react'
import {
  type ConsumerImpact,
  type ImpactLevel,
  isNoUseCase,
  type QuestionImpact,
  type UseCaseImpact,
  useConsumerImpact,
} from '@/api/consumer-impact'
import { CLASSIFICATION_LABEL, type Classification } from '@/api/ontology-diff'
import { ErrorAlert } from '@/components/ErrorAlert'
import { SeveritySwatch } from '@/components/SeveritySwatch'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import { causesOf, IMPACT_LABEL, impactSections, type ImpactSection } from '@/lib/consumer-impact'
import { cn } from '@/lib/utils'

/** The Diff colour each level is keyed by: what makes it affected, or will-be-affected. */
const LEVEL_SEVERITY: Record<ImpactLevel, Classification | null> = {
  affected: 'breaking',
  will_be_affected: 'deprecating',
  unknown: null,
}

interface ConsumerImpactPanelProps {
  knowledgeGraph: string
  base: number
  target: number
  className?: string
}

/**
 * Loads and shows the Consumer impact of the Ontology Diff from version `base` to
 * `target`, judged against the latest Use Case Version; says so when there is no Use Case.
 * Beside the changes on the Compare page and the Changes tab.
 */
export function ConsumerImpactPanel({ knowledgeGraph, base, target, className }: ConsumerImpactPanelProps) {
  const impact = useConsumerImpact(knowledgeGraph, base, target)
  if (impact.isError && isNoUseCase(impact.error)) {
    return (
      <ImpactRegion className={className}>
        <p className="text-sm text-muted-foreground">
          This Knowledge Graph has no Use Case, so there are no Consumers to judge this change against.
        </p>
      </ImpactRegion>
    )
  }
  if (impact.isError) return <ErrorAlert error={impact.error} />
  if (impact.isPending) return <Skeleton className={cn('h-24 w-full', className)} />
  return <ConsumerImpactView impact={impact.data} className={className} />
}

/**
 * Consumer impact that is already loaded: a section per level (affected, will be affected,
 * impact unknown), each listing its Consumers with the Tasks and Competency Questions hit
 * and the Concepts that hit them, then the questions at that level no Task needs. A
 * region named "Consumer impact".
 */
export function ConsumerImpactView({ impact, className }: { impact: UseCaseImpact; className?: string }) {
  const sections = impactSections(impact)
  return (
    <ImpactRegion className={className}>
      {sections.length === 0 ? (
        <p className="text-sm text-muted-foreground">No Consumer, Task or Competency Question is hit.</p>
      ) : (
        sections.map((section) => <Section key={section.level} section={section} />)
      )}
    </ImpactRegion>
  )
}

function ImpactRegion({ className, children }: { className?: string; children: ReactNode }) {
  const titleId = useId()
  return (
    <section aria-labelledby={titleId} className={cn('space-y-3', className)}>
      <h3 id={titleId} className="text-sm font-semibold">
        Consumer impact
      </h3>
      {children}
    </section>
  )
}

function Section({ section }: { section: ImpactSection }) {
  const titleId = useId()
  const severity = LEVEL_SEVERITY[section.level]
  return (
    <section aria-labelledby={titleId} className="space-y-2">
      <h4 id={titleId} className="flex items-center gap-2 text-xs font-medium text-muted-foreground">
        {severity && <SeveritySwatch level={severity} />}
        {IMPACT_LABEL[section.level]}
      </h4>
      {section.level === 'unknown' && (
        <p className="text-xs text-muted-foreground">
          These questions have neither a Concept mapping nor a query, so it cannot be told what they need.
        </p>
      )}
      {section.consumers.length > 0 && (
        <ul aria-label={`${IMPACT_LABEL[section.level]} Consumers`} className="space-y-2">
          {section.consumers.map((consumer) => (
            <ConsumerItem key={consumer.id} consumer={consumer} />
          ))}
        </ul>
      )}
      {section.noConsumer.length > 0 && (
        <div className="space-y-1 rounded-lg border border-dashed p-3">
          <p className="text-xs font-medium">No Consumer</p>
          <Questions questions={section.noConsumer} label={`${IMPACT_LABEL[section.level]} questions no Task needs`} />
        </div>
      )}
    </section>
  )
}

function ConsumerItem({ consumer }: { consumer: ConsumerImpact }) {
  const titleId = useId()
  return (
    <li
      aria-labelledby={titleId}
      className="min-w-0 space-y-2 rounded-lg bg-card p-3 text-sm text-card-foreground ring-1 ring-foreground/10"
    >
      <div className="flex flex-wrap items-center gap-2">
        <span id={titleId} className="font-semibold">
          {consumer.name}
        </span>
        {consumer.kind && <Badge variant="secondary">{consumer.kind}</Badge>}
        <code className="font-mono text-xs text-muted-foreground">{consumer.id}</code>
      </div>
      <ul aria-label={`Tasks of ${consumer.name} hit`} className="space-y-2">
        {consumer.tasks.map((task) => (
          <li key={task.id} className="space-y-1 border-l-2 pl-3">
            <p>
              {task.description} <code className="font-mono text-xs text-muted-foreground">{task.id}</code>
              {task.level !== consumer.level && (
                <span className="ml-2 text-xs text-muted-foreground">({IMPACT_LABEL[task.level].toLowerCase()})</span>
              )}
            </p>
            <Questions questions={task.questions} label={`Competency Questions of ${task.id} hit`} />
          </li>
        ))}
      </ul>
    </li>
  )
}

function Questions({ questions, label }: { questions: QuestionImpact[]; label: string }) {
  return (
    <ul aria-label={label} className="space-y-0.5 text-xs">
      {questions.map((q) => (
        <li key={q.id} className="flex flex-wrap items-center gap-x-2 gap-y-0.5">
          <code className="font-mono">{q.id}</code>
          <span className="text-muted-foreground">{q.question}</span>
          {causesOf(q).map((cause) => (
            <span key={cause.concept} className="inline-flex items-center gap-1 font-mono">
              <SeveritySwatch level={cause.classification} />
              {cause.concept}
              <span className="sr-only"> ({CLASSIFICATION_LABEL[cause.classification]})</span>
            </span>
          ))}
        </li>
      ))}
    </ul>
  )
}
