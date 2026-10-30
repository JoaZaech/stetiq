import type { ReactNode } from 'react'
import { useCanEdit } from '@/api/whoami'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'

interface NeedsEditAccessProps {
  knowledgeGraph: string
  /** Renders the edit control; `disabled` is true when the user lacks `edit`. */
  children: (disabled: boolean) => ReactNode
}

/**
 * Wraps an edit control (Promote, Edit description, Add Competency Question...) so
 * that, without `edit` on `knowledgeGraph`, it stays visible but disabled with a
 * "Needs edit access" tooltip. The server still checks every write.
 *
 *   <NeedsEditAccess knowledgeGraph={name}>
 *     {(disabled) => <Button disabled={disabled}>Promote</Button>}
 *   </NeedsEditAccess>
 */
export function NeedsEditAccess({ knowledgeGraph, children }: NeedsEditAccessProps) {
  const allowed = useCanEdit(knowledgeGraph)
  if (allowed) return children(false)
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        {/* A disabled button gets no pointer events, so the tooltip hangs on a wrapper. */}
        <span tabIndex={0} className="inline-flex">
          {children(true)}
        </span>
      </TooltipTrigger>
      <TooltipContent>Needs edit access</TooltipContent>
    </Tooltip>
  )
}
