import type { RouteHandle } from '@/app/breadcrumbs'
import { guidePage } from './guide'

/** `/help/:page`'s breadcrumb: the page's title (`Help › Getting started`). */
export const helpPageHandle: RouteHandle = {
  crumb: ({ page }) => guidePage(page)?.title ?? 'Page not found',
}
