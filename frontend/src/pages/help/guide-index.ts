/** One page of the user guide (`docs/guide/`, ADR 0004). */
export interface GuidePage {
  /** In the URL: `/help/<slug>`. The filename without its number prefix and `.md`. */
  slug: string
  /** The page's first `#` heading. */
  title: string
  markdown: string
}

const GUIDE_FILE = /^(?:(\d+)-)?(.+)\.md$/

/**
 * The guide's pages in reading order, from a map of file path → Markdown (as Vite's glob
 * import hands them over). Order comes from the filename's number prefix (`01-`, `02-`…);
 * files without one come last, by filename. A page without a `#` heading is titled by its slug.
 */
export function guidePages(files: Record<string, string>): GuidePage[] {
  return Object.entries(files)
    .map(([path, markdown]) => {
      const [, prefix, slug] = GUIDE_FILE.exec(fileName(path)) ?? []
      const order = prefix === undefined ? Infinity : Number(prefix)
      return { order, slug, title: firstHeading(markdown) ?? slug, markdown }
    })
    .sort((a, b) => a.order - b.order || a.slug.localeCompare(b.slug))
    .map(({ slug, title, markdown }) => ({ slug, title, markdown }))
}

function fileName(path: string): string {
  return path.slice(path.lastIndexOf('/') + 1)
}

function firstHeading(markdown: string): string | undefined {
  return /^# +(.+?)\s*#*\s*$/m.exec(markdown)?.[1]
}

/** The in-app route of a guide page, relative to the router's `/ui` basename. */
export function helpUrl(slug: string): string {
  return `/help/${slug}`
}

/** `./04-cli.md#tracking-uri`: a file next to the current one, as written on GitHub. */
const GUIDE_LINK = /^(?:\.\/)?([^/:#?]+\.md)(#.*)?$/

/**
 * The in-app Help route a guide link points to (`./04-cli.md#tracking-uri` →
 * `/help/cli#tracking-uri`), or `undefined` when it is not a link to another guide file:
 * external links, in-page anchors and files outside `docs/guide/` are left alone.
 */
export function guideLink(href: string): string | undefined {
  const [, file, anchor = ''] = GUIDE_LINK.exec(href) ?? []
  if (file === undefined) return undefined
  const [, , slug] = GUIDE_FILE.exec(file) ?? []
  return helpUrl(slug) + anchor
}
