import { useEffect, type ReactNode } from 'react'

interface PageHeaderProps {
  title: string
  /** Shown in the heading after `title`, e.g. a run's params as chips; not in the tab title. */
  titleExtra?: ReactNode
  /** The browser tab title, when it should differ from `title`. */
  tabTitle?: string
  /** One line under the title. */
  description?: ReactNode
  /** Buttons on the right, e.g. Promote or Compare. */
  actions?: ReactNode
}

/** The title block every page starts with; also sets the browser tab title. */
export function PageHeader({ title, titleExtra, tabTitle = title, description, actions }: PageHeaderProps) {
  useEffect(() => {
    document.title = `${tabTitle} · stetiq`
  }, [tabTitle])

  return (
    <header className="mb-6 flex flex-wrap items-start justify-between gap-4">
      <div className="min-w-0">
        {titleExtra ? (
          <h1 className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xl font-semibold tracking-tight">
            <span className="truncate">{title}</span>
            {titleExtra}
          </h1>
        ) : (
          <h1 className="truncate text-xl font-semibold tracking-tight">{title}</h1>
        )}
        {description && <p className="mt-1 text-sm text-muted-foreground">{description}</p>}
      </div>
      {actions && <div className="flex shrink-0 items-center gap-2">{actions}</div>}
    </header>
  )
}
