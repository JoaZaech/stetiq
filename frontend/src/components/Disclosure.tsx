import { ChevronDown, ChevronRight } from 'lucide-react'
import { type ReactNode, useId, useState } from 'react'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'

interface DisclosureProps {
  /** The toggle's text, e.g. "Show all metrics" or "3 passed". */
  label: ReactNode
  children: ReactNode
  /** Make it a `section` headed by the toggle (an `h2`), named by the label. */
  heading?: boolean
  defaultOpen?: boolean
  className?: string
}

/** Content folded behind a chevron toggle, closed until opened. */
export function Disclosure({ label, children, heading = false, defaultOpen = false, className }: DisclosureProps) {
  const [open, setOpen] = useState(defaultOpen)
  const id = useId()
  const Chevron = open ? ChevronDown : ChevronRight
  const toggle = (
    <Button
      id={`${id}-toggle`}
      variant="ghost"
      size="sm"
      className={cn('-ml-2 h-7 px-2 text-sm', heading && 'font-semibold')}
      aria-expanded={open}
      aria-controls={`${id}-body`}
      onClick={() => setOpen(!open)}
    >
      <Chevron aria-hidden className="size-4" />
      {label}
    </Button>
  )
  const body = (
    <div id={`${id}-body`} hidden={!open} className="pt-2">
      {children}
    </div>
  )
  return heading ? (
    <section aria-labelledby={`${id}-toggle`} className={cn('min-w-0', className)}>
      <h2>{toggle}</h2>
      {body}
    </section>
  ) : (
    <div className={cn('min-w-0', className)}>
      {toggle}
      {body}
    </div>
  )
}
