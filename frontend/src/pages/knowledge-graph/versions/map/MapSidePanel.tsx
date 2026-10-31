import type { ReactNode } from 'react'
import { X } from 'lucide-react'
import { Button } from '@/components/ui/button'

/**
 * A panel beside the Map, named `label`: a header of what it is about (`kind`, `title`
 * and an optional `subtitle`) with a Close button, then `children`.
 */
export function MapSidePanel({
  label,
  kind,
  title,
  subtitle,
  onClose,
  children,
}: {
  label: string
  kind: string
  title: ReactNode
  subtitle?: ReactNode
  onClose: () => void
  children: ReactNode
}) {
  return (
    <aside aria-label={label} className="w-80 shrink-0 space-y-4 overflow-y-auto border-l bg-background p-4 text-sm">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="text-xs text-muted-foreground">{kind}</div>
          <h3 className="font-semibold break-words">{title}</h3>
          {subtitle}
        </div>
        <Button variant="ghost" size="icon-sm" aria-label={`Close ${label.toLowerCase()}`} onClick={onClose}>
          <X aria-hidden />
        </Button>
      </div>
      {children}
    </aside>
  )
}
