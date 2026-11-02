import type { ReactNode } from 'react'
import { STATUS_TONES } from '@/components/status-tones'
import { StatusLabel } from '@/components/StatusLabel'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { formatCount, formatPercent } from '@/lib/format'
import { conformanceTone, type RunGate, sourceList } from './runs'

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

/** A `sources` param as "5 sources", each source in a tooltip. */
export function SourcesLabel({ value }: { value: string }) {
  const sources = sourceList(value)
  return (
    <WithTooltip
      tip={
        <ul aria-label="Sources" className="font-mono text-xs">
          {sources.map((s) => (
            <li key={s}>{s}</li>
          ))}
        </ul>
      }
    >
      <span tabIndex={0} className="tabular-nums underline decoration-dotted underline-offset-4">
        {formatCount(sources.length, 'source')}
      </span>
    </WithTooltip>
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
