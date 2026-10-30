import type { RouteHandle } from '@/app/breadcrumbs'
import { GUIDE } from './guide'

/** `/help/:page`'s breadcrumb: the page's title (`Help › Getting started`). */
export const helpPageHandle: RouteHandle = {
  crumb: ({ page }) => GUIDE.find((p) => p.slug === page)?.title ?? 'Page not found',
}
