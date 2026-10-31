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

/**
 * The vision (`docs/vision.md`), bundled the same way: the web UI's "Planned" placeholders
 * link to it, at `/help/vision`. It is listed apart from the guide, which describes only
 * what is built.
 */
export const [VISION] = guidePages(
  import.meta.glob<string>('../../../../docs/vision.md', {
    query: '?raw',
    import: 'default',
    eager: true,
  }),
)

/** The Help page at `/help/<slug>`, or `undefined` when there is none. */
export function guidePage(slug: string | undefined): GuidePage | undefined {
  return [...GUIDE, VISION].find((page) => page.slug === slug)
}
