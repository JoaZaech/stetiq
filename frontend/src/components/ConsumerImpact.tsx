import { ChevronDown, ChevronRight, type LucideIcon } from 'lucide-react'
import { type ReactNode, useId, useState } from 'react'
import {
  type ImpactLevel,
  isNoUseCase,
  type QuestionImpact,
  type UseCaseImpact,
  useConsumerImpact,
} from '@/api/consumer-impact'
import { CLASSIFICATION_LABEL } from '@/api/ontology-diff'
import { ErrorAlert } from '@/components/ErrorAlert'
import { StatusLabel } from '@/components/StatusLabel'
import { SEVERITY } from '@/components/severity-style'
import { STATUS_TONES } from '@/components/status-tones'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import { causesOf, IMPACT_LABEL, type ImpactItem, impactItems } from '@/lib/consumer-impact'
import { cn } from '@/lib/utils'

/** A level's mark: the Diff colour of what causes it (as `SEVERITY`), neutral when unknown. */
const LEVEL_MARK: Record<ImpactLevel, { Icon: LucideIcon; className: string; border: string }> = {
  affected: { Icon: STATUS_TONES.failure.Icon, className: SEVERITY.text.breaking, border: SEVERITY.border.breaking },
  will_be_affected: {
    Icon: STATUS_TONES.warning.Icon,
    className: SEVERITY.text.deprecating,
    border: SEVERITY.border.deprecating,
  },
  unknown: { ...STATUS_TONES.neutral, border: 'border-border' },
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
 * Beside the changes on the Compare page and the Changes tab, and in the Promote dialog.
 */
export function ConsumerImpactPanel({ knowledgeGraph, base, target, className }: ConsumerImpactPanelProps) {
  const impact = useConsumerImpact(knowledgeGraph, base, target)
  if (impact.isError && isNoUseCase(impact.error)) {
    return (
      <ImpactRegion className={className}>
        <p className="text-sm text-muted-foreground">
          This Knowledge Graph has no Use Case, so no Consumers are declared to judge this change against.
        </p>
      </ImpactRegion>
    )
  }
  if (impact.isError) return <ErrorAlert error={impact.error} />
  if (impact.isPending) return <Skeleton className={cn('h-24 w-full', className)} />
  return <ConsumerImpactView impact={impact.data} className={className} />
}

/**
 * Consumer impact that is already loaded, as a list of items: one per hit Task, with its
 * level's icon, its Consumer and why it is hit, expanding to the Competency Questions hit
 * and the Concepts that hit them; then the hit questions no Task needs. A region named
 * "Consumer impact".
 */
export function ConsumerImpactView({ impact, className }: { impact: UseCaseImpact; className?: string }) {
  const items = impactItems(impact)
  return (
    <ImpactRegion className={className}>
      {items.length === 0 ? (
        <p className="text-sm">
          <StatusLabel tone="success" label="No Consumer is affected" />
        </p>
      ) : (
        <ul aria-label="Tasks and questions hit" className="space-y-2">
          {items.map((item) => (
            <Item key={item.key} item={item} />
          ))}
        </ul>
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

function Item({ item }: { item: ImpactItem }) {
  const id = useId()
  const [open, setOpen] = useState(false)
  const { Icon, className, border } = LEVEL_MARK[item.level]
  // A question no Task needs is already its own title: there is nothing to expand to.
  const expands = item.consumer !== null
  const Chevron = open ? ChevronDown : ChevronRight
  const header = (
    <>
      <Icon aria-hidden className={cn('mt-0.5 size-4 shrink-0', className)} />
      <span className="sr-only">{IMPACT_LABEL[item.level]}: </span>
      <span className="min-w-0 flex-1 space-y-0.5">
        <span className="flex flex-wrap items-center gap-2">
          <span id={`${id}-title`} className="font-medium">
            {item.title}
          </span>
          {item.consumer === null ? (
            <Badge variant="outline" className="text-muted-foreground">
              No Consumer
            </Badge>
          ) : (
            <Badge variant="secondary">{item.consumer}</Badge>
          )}
        </span>
        <span className="block text-xs text-muted-foreground">{item.reason}</span>
      </span>
    </>
  )
  return (
    <li
      aria-labelledby={`${id}-title`}
      className={cn(
        'min-w-0 rounded-lg border-l-4 bg-card text-sm text-card-foreground ring-1 ring-foreground/10',
        border,
      )}
    >
      {expands ? (
        <button
          type="button"
          className="flex w-full items-start gap-2 rounded-lg p-3 text-left outline-none hover:bg-muted/50 focus-visible:ring-[3px] focus-visible:ring-ring/50"
          aria-expanded={open}
          aria-controls={`${id}-body`}
          onClick={() => setOpen(!open)}
        >
          {header}
          <Chevron aria-hidden className="mt-0.5 size-4 shrink-0 text-muted-foreground" />
        </button>
      ) : (
        <div className="flex items-start gap-2 p-3">{header}</div>
      )}
      {expands && (
        <div id={`${id}-body`} hidden={!open} className="px-3 pb-3 pl-9">
          <Questions questions={item.questions} />
        </div>
      )}
    </li>
  )
}

/** Each question hit, followed by the Concepts that hit it, in their classification's colour. */
function Questions({ questions }: { questions: QuestionImpact[] }) {
  return (
    <ul aria-label="Competency Questions hit" className="space-y-1.5 text-xs">
      {questions.map((q) => (
        <li key={q.id} className="flex flex-wrap items-center gap-x-2 gap-y-1">
          <span>{q.question}</span>
          {causesOf(q).map(({ concept, classification }) => (
            <Badge
              key={concept}
              variant="outline"
              className={cn(
                'font-mono',
                SEVERITY.border[classification],
                SEVERITY.fill[classification],
                SEVERITY.text[classification],
              )}
            >
              {concept}
              <span className="sr-only"> ({CLASSIFICATION_LABEL[classification]})</span>
            </Badge>
          ))}
        </li>
      ))}
    </ul>
  )
}
