import type { ComponentProps, ReactNode } from 'react'
import { ArrowLeft, PanelRightClose, X } from 'lucide-react'
import { Button } from '@/components/ui/button'

/**
 * How a panel is left: a `back` link to the panel it came from (such as the change
 * summary) or a Close button (`onClose`), and `onCollapse`, when the panel can shrink to
 * a rail. Each shows only when given.
 */
export interface MapPanelNav {
  back?: { label: string; onBack: () => void }
  onClose?: () => void
  onCollapse?: () => void
}

/**
 * The one panel beside the Map, on its right, named `label`: its `nav`, a header of what
 * it is about (an optional `kind`, `title` and an optional `subtitle`), then `children`.
 */
export function MapSidePanel({
  label,
  kind,
  title,
  subtitle,
  nav: { back, onClose, onCollapse },
  children,
  ...props
}: {
  label: string
  kind?: string
  title: ReactNode
  subtitle?: ReactNode
  nav: MapPanelNav
  children: ReactNode
} & Omit<ComponentProps<'aside'>, 'title'>) {
  return (
    <aside
      aria-label={label}
      className="w-80 shrink-0 space-y-4 overflow-y-auto border-l bg-background p-4 text-sm"
      {...props}
    >
      {back && (
        <Button variant="link" size="sm" className="h-auto p-0 text-muted-foreground" onClick={back.onBack}>
          <ArrowLeft aria-hidden />
          {back.label}
        </Button>
      )}
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          {kind && <div className="text-xs text-muted-foreground">{kind}</div>}
          <h3 className="font-semibold break-words">{title}</h3>
          {subtitle}
        </div>
        <div className="flex shrink-0">
          {onCollapse && (
            <Button variant="ghost" size="icon-sm" aria-label="Collapse panel" onClick={onCollapse}>
              <PanelRightClose aria-hidden />
            </Button>
          )}
          {onClose && (
            <Button variant="ghost" size="icon-sm" aria-label={`Close ${label.toLowerCase()}`} onClick={onClose}>
              <X aria-hidden />
            </Button>
          )}
        </div>
      </div>
      {children}
    </aside>
  )
}
