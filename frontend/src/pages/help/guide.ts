import { type GuidePage, guidePages } from './guide-index'

/**
 * The user guide, bundled as raw Markdown at build time (ADR 0004). Add a page by adding a
 * numbered file to `docs/guide/`; this module is only loaded with the Help pages.
 */
export const GUIDE = guidePages(
  import.meta.glob<string>('../../../../docs/guide/*.md', {
    query: '?raw',
    import: 'default',
    eager: true,
  }),
)

/** The guide page at `/help/<slug>`, or `undefined` when there is none. */
export function guidePage(slug: string | undefined): GuidePage | undefined {
  return GUIDE.find((page) => page.slug === slug)
}
