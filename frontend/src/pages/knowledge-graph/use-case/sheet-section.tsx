import { useId, type ReactNode } from 'react'

interface SheetSectionProps {
  title: string
  /** Controls beside the title. */
  actions?: ReactNode
  children: ReactNode
}

/** A titled section of a side sheet, a region named by its title. */
export function SheetSection({ title, actions, children }: SheetSectionProps) {
  const id = useId()
  return (
    <section aria-labelledby={id} className="space-y-2">
      <div className="flex items-center justify-between gap-2">
        <h3 id={id} className="text-xs font-medium text-muted-foreground">
          {title}
        </h3>
        {actions}
      </div>
      {children}
    </section>
  )
}
