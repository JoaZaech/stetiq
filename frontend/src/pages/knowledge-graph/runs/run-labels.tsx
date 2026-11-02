import type { ReactNode } from 'react'
import { STATUS_TONES } from '@/components/status-tones'
import { StatusLabel } from '@/components/StatusLabel'
import { Badge } from '@/components/ui/badge'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { formatPercent } from '@/lib/format'
import { conformanceTone, paramChips, type RunGate } from './runs'

const formatParam = ([key, value]: [string, string]) => `${key}: ${value}`

function WithTooltip({ tip, children }: { tip: ReactNode; children: ReactNode }) {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <span className="inline-flex">{children}</span>
      </TooltipTrigger>
      <TooltipContent>{tip}</TooltipContent>
    </Tooltip>
  )
}

/**
 * A run's first params as chips (`extractor: llm`), the rest as "+n" with them in a
 * tooltip. A chip is never wider than `max-w-48`: a long value is cut with an ellipsis,
 * and pointing at the chip shows it whole. Spans, so it can sit in a heading.
 */
export function ParamChips({ params }: { params: Readonly<Record<string, string>> }) {
  const { shown, hidden } = paramChips(params)
  if (shown.length === 0) return null
  return (
    <span role="list" aria-label="Params" className="inline-flex flex-wrap items-center gap-1">
      {shown.map((param) => (
        <span role="listitem" key={param[0]}>
          <WithTooltip tip={formatParam(param)}>
            <Badge variant="outline" className="max-w-48 font-mono font-normal">
              <span className="min-w-0 truncate">{formatParam(param)}</span>
            </Badge>
          </WithTooltip>
        </span>
      ))}
      {hidden.length > 0 && (
        <span role="listitem">
          <WithTooltip tip={hidden.map(formatParam).join(', ')}>
            <Badge variant="secondary" className="font-normal">
              +{hidden.length}
            </Badge>
          </WithTooltip>
        </span>
      )}
    </span>
  )
}

/** A Conformance score as a percentage, coloured by how close it is to 100 %. */
export function ConformancePercent({ score }: { score: number }) {
  return <span className={`tabular-nums ${STATUS_TONES[conformanceTone(score)].className}`}>{formatPercent(score)}</span>
}

/**
 * A run's Gate column: its recorded Gate result; else its Gate Preview, neutral because
 * it is not recorded (ADR 0007); else "—".
 */
export function RunGateLabel({ gate }: { gate: RunGate }) {
  switch (gate.kind) {
    case 'recorded':
      return <StatusLabel tone={gate.passed ? 'success' : 'failure'} label={gate.passed ? 'Passed' : 'Failed'} />
    case 'preview':
      return (
        <WithTooltip
          tip={`Gate Preview: ${gate.passed ? 'passes' : 'fails'} when judged against current Gates. Not recorded: only a Gate result CI records counts.`}
        >
          <StatusLabel tone="neutral" label="Preview" />
        </WithTooltip>
      )
    case 'none':
      return <span className="text-muted-foreground">—</span>
  }
}
