import { NavLink } from 'react-router'
import { cn } from '@/lib/utils'

export interface RouteTab {
  label: string
  /** Relative to the page's route; `''` is its index (the default tab). */
  to: string
}

/**
 * Tabs that are routes, so every tab has its own URL. Each tab's page is a child
 * route of the page in `router.tsx`, rendered by the page's `<Outlet />`.
 */
export function RouteTabs({ label, tabs }: { label: string; tabs: readonly RouteTab[] }) {
  return (
    <nav aria-label={label} className="mb-6 flex gap-4 border-b text-sm">
      {tabs.map((tab) => (
        <NavLink
          key={tab.to}
          to={tab.to}
          end={tab.to === ''}
          className={({ isActive }) =>
            cn(
              '-mb-px border-b-2 px-1 pb-2 font-medium transition-colors',
              isActive
                ? 'border-primary text-foreground'
                : 'border-transparent text-muted-foreground hover:text-foreground',
            )
          }
        >
          {tab.label}
        </NavLink>
      ))}
    </nav>
  )
}
