import { Info } from 'lucide-react'
import { Link } from 'react-router'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'

/**
 * An ⓘ that explains what is beside it in a tooltip of at most two sentences, and links
 * to the guide page (`/ui/help/...`) that says more. The page itself carries no
 * explanatory sentences: they go here.
 */
export function InfoTip({ label, children, to }: { label: string; children: string; to?: string }) {
  const icon = <Info aria-hidden className="size-3.5" />
  const className = 'inline-flex items-center text-muted-foreground hover:text-foreground'
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        {to ? (
          <Link to={to} aria-label={`About ${label}`} className={className}>
            {icon}
          </Link>
        ) : (
          <button type="button" aria-label={`About ${label}`} className={className}>
            {icon}
          </button>
        )}
      </TooltipTrigger>
      <TooltipContent className="max-w-xs">{children}</TooltipContent>
    </Tooltip>
  )
}
