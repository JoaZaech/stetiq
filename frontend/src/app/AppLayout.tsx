import { Fragment, Suspense } from 'react'
import { Link, Outlet, useMatches } from 'react-router'
import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbList,
  BreadcrumbPage,
  BreadcrumbSeparator,
} from '@/components/ui/breadcrumb'
import { Separator } from '@/components/ui/separator'
import { Skeleton } from '@/components/ui/skeleton'
import { SidebarInset, SidebarProvider, SidebarTrigger } from '@/components/ui/sidebar'
import { AppSidebar } from './AppSidebar'
import { breadcrumbs } from './breadcrumbs'

/** shadcn's sidebar writes its open state to this cookie; read it back on load. */
function sidebarWasOpen(): boolean {
  return !document.cookie.split('; ').includes('sidebar_state=false')
}

/**
 * The sidebar plus the rounded main card holding the breadcrumbs and the page.
 *
 * On Help it must not ask for session data (`/api/v1`): Help renders in it signed out,
 * and in server mode any such request sends a signed-out reader to sign-in. The
 * sidebar's Knowledge Graph list is the one exception elsewhere (see `AppSidebar`).
 */
export function AppLayout() {
  return (
    <SidebarProvider defaultOpen={sidebarWasOpen()}>
      <AppSidebar />
      <SidebarInset>
        <div className="flex h-12 shrink-0 items-center gap-2 border-b px-4">
          <SidebarTrigger className="-ml-1" />
          <Separator orientation="vertical" className="mr-2 h-4! self-center" />
          <Breadcrumbs />
        </div>
        <main className="flex-1 p-6">
          {/* While a lazily loaded page (router.tsx) arrives on a first visit. */}
          <Suspense fallback={<Skeleton className="h-32 w-full" />}>
            <Outlet />
          </Suspense>
        </main>
      </SidebarInset>
    </SidebarProvider>
  )
}

function Breadcrumbs() {
  const crumbs = breadcrumbs(useMatches())
  return (
    <Breadcrumb>
      <BreadcrumbList>
        {crumbs.map((crumb, i) => (
          <Fragment key={crumb.to + i}>
            {i > 0 && <BreadcrumbSeparator />}
            <BreadcrumbItem>
              {i === crumbs.length - 1 ? (
                <BreadcrumbPage>{crumb.label}</BreadcrumbPage>
              ) : (
                <BreadcrumbLink asChild>
                  <Link to={crumb.to}>{crumb.label}</Link>
                </BreadcrumbLink>
              )}
            </BreadcrumbItem>
          </Fragment>
        ))}
      </BreadcrumbList>
    </Breadcrumb>
  )
}
