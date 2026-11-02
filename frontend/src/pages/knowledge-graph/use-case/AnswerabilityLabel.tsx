import { StatusLabel } from '@/components/StatusLabel'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { ANSWERABILITY_LABELS, type AnswerabilityStatus } from './answerability'

/** A Competency Question's answerability as its status icon and name; "Can't check" explains itself in a tooltip. */
export function AnswerabilityLabel({ status }: { status: AnswerabilityStatus }) {
  const { tone, label, hint } = ANSWERABILITY_LABELS[status]
  if (!hint) return <StatusLabel tone={tone} label={label} />
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <span className="inline-flex">
          <StatusLabel tone={tone} label={label} />
        </span>
      </TooltipTrigger>
      <TooltipContent>{hint}</TooltipContent>
    </Tooltip>
  )
}
