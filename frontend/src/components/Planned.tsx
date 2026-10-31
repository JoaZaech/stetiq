import type { ReactNode } from 'react'
import { Link } from 'react-router'
import { badgeVariants } from '@/components/ui/badge'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { cn } from '@/lib/utils'
import { helpUrl } from '@/pages/help/guide-index'

/** The sections of the vision (`docs/vision.md`, at `/help/vision`) a placeholder can link to. */
export type VisionSection =
  | 'the-two-gate-pipeline'
  | 'consumer-gate'
  | 'connector'
  | 'consumer-impact-and-gates-over-it'
  | 'ai-and-mcp-authoring'

/** App path (under `/ui`) of a section of the vision. */
function visionUrl(section: VisionSection): string {
  return `${helpUrl('vision')}#${section}`
}

interface PlannedProps {
  /** What is planned, in GLOSSARY.md's words: names the stand-in and its link. */
  label: string
  /** The section of the vision that describes it. */
  section: VisionSection
  /** One sentence on what it will do, shown in the tooltip. */
  tooltip: string
  /** The disabled stand-in: muted text, or a control rendered `disabled`. */
  children: ReactNode
  className?: string
}

/**
 * A feature of the downstream vision that the web UI shows but does not build: a muted,
 * disabled stand-in (`children`, a `group` named `label`), then a "Planned" badge that
 * explains it in a tooltip and links to its section of the vision.
 *
 *   <Planned label="Connector" section="connector" tooltip="…">Connector: not connected</Planned>
 */
export function Planned({ label, section, tooltip, children, className }: PlannedProps) {
  return (
    <span className={cn('inline-flex flex-wrap items-center gap-1.5', className)}>
      <span role="group" aria-label={label} aria-disabled="true" className="text-muted-foreground">
        {children}
      </span>
      <Tooltip>
        <TooltipTrigger asChild>
          <Link
            to={visionUrl(section)}
            aria-label={`Planned: ${label}`}
            className={cn(badgeVariants({ variant: 'outline' }), 'border-dashed text-muted-foreground')}
          >
            Planned
          </Link>
        </TooltipTrigger>
        <TooltipContent>{tooltip} Not built yet: open the vision to read more.</TooltipContent>
      </Tooltip>
    </span>
  )
}
