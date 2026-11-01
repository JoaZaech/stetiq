import { useEffect } from 'react'
import { Navigate, NavLink, useLocation, useParams } from 'react-router'
import { cn } from '@/lib/utils'
import { NotFoundPage } from '@/pages/NotFoundPage'
import { GUIDE, guidePage, VISION } from './guide'
import type { GuidePage } from './guide-index'
import { helpUrl } from './guide-index'
import { GuideMarkdown } from './GuideMarkdown'

/** `/help`: the first page of the guide. */
export function HelpIndex() {
  return <Navigate to={helpUrl(GUIDE[0].slug)} replace />
}

/** `/help/:page`: one page of the user guide, next to the guide's table of contents. */
export function HelpPage() {
  const slug = useParams().page
  const page = guidePage(slug)

  useEffect(() => {
    if (page) document.title = `${page.title} · stetiq`
  }, [page])
  useScrollToAnchor(page?.slug)

  if (!page) return <NotFoundPage />
  return (
    <div className="flex flex-col-reverse gap-8 lg:flex-row lg:items-start">
      <article className="min-w-0 flex-1">
        <GuideMarkdown from={page.path}>{page.markdown}</GuideMarkdown>
      </article>
      <GuideContents />
    </div>
  )
}

/**
 * Every guide page, in order, then the vision; the current page is highlighted
 * (`aria-current`).
 */
function GuideContents() {
  return (
    <nav aria-label="Guide" className="shrink-0 space-y-4 lg:sticky lg:top-4 lg:w-56">
      <ContentsList heading="User guide" pages={GUIDE} />
      <ContentsList heading="Planned" pages={[VISION]} />
    </nav>
  )
}

function ContentsList({ heading, pages }: { heading: string; pages: GuidePage[] }) {
  return (
    <div>
      <p className="mb-2 text-xs font-medium text-muted-foreground">{heading}</p>
      <ul className="space-y-0.5 text-sm">
        {pages.map(({ slug, title }) => (
          <li key={slug}>
            <NavLink
              to={helpUrl(slug)}
              className={({ isActive }) =>
                cn(
                  'block rounded-md px-2 py-1 hover:bg-accent',
                  isActive && 'bg-accent font-medium text-accent-foreground',
                )
              }
            >
              {title}
            </NavLink>
          </li>
        ))}
      </ul>
    </div>
  )
}

/**
 * The router does not scroll to a URL's `#anchor`: on a deep link and on in-app
 * navigation, scroll to that heading once the page has rendered, else to the top.
 */
function useScrollToAnchor(page: string | undefined) {
  const { hash } = useLocation()
  useEffect(() => {
    const target = hash && document.getElementById(decodeURIComponent(hash.slice(1)))
    if (target) target.scrollIntoView()
    else window.scrollTo(0, 0)
  }, [page, hash])
}
