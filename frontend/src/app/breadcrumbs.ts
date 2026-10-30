/** Route params, as React Router hands them over. */
export type RouteParams = Record<string, string | undefined>

/**
 * What a route in `router.tsx` may declare in its `handle`. A route with a `crumb`
 * adds one breadcrumb, linking to the path that route matched.
 */
export interface RouteHandle {
  crumb?: (params: RouteParams) => string
}

export interface Crumb {
  label: string
  to: string
}

interface MatchLike {
  pathname: string
  params: RouteParams
  handle: unknown
}

export function breadcrumbs(matches: readonly MatchLike[]): Crumb[] {
  return matches.flatMap(({ pathname, params, handle }) => {
    const crumb = (handle as RouteHandle | null | undefined)?.crumb
    return crumb ? [{ label: crumb(params), to: pathname }] : []
  })
}
