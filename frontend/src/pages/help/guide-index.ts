/**
 * One page of Help: a page of the user guide (`docs/guide/`, ADR 0004), or the vision
 * (`docs/vision.md`), which the guide's planned features link to.
 */
export interface GuidePage {
  /** In the URL: `/help/<slug>`. The filename without its number prefix and `.md`. */
  slug: string
  /** Its source in the repository, e.g. `docs/guide/04-cli.md`: what its relative links start from. */
  path: string
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
      return { order, slug, path: repoPath(path), title: firstHeading(markdown) ?? slug, markdown }
    })
    .sort((a, b) => a.order - b.order || a.slug.localeCompare(b.slug))
    .map(({ slug, path, title, markdown }) => ({ slug, path, title, markdown }))
}

/** A glob import's path (`../../../../docs/guide/04-cli.md`) as a repository path. */
function repoPath(path: string): string {
  return path.replace(/^(?:\.\.?\/)+/, '')
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

/** The repository files bundled into Help: the guide's pages and the vision. */
const BUNDLED = /^docs\/(?:guide\/[^/]+|vision)\.md$/

/** Where links to repository files that Help does not bundle go. */
const REPO_BLOB_URL = 'https://github.com/JoaZaech/stetiq/blob/main/'

/** A link with a scheme (`https:`, `mailto:`) or an in-page anchor. */
const NOT_RELATIVE = /^(?:[a-z][a-z0-9+.-]*:|#|\/)/i

/**
 * Where a link in the Help page whose source is `from` goes, written as on GitHub (relative
 * to that file): a `route` inside the app when it points to another bundled page
 * (`./04-cli.md#tracking-uri` → `/help/cli#tracking-uri`), else a `url`. Other files in the
 * repository (`../GLOSSARY.md`) are not in the app, so they open on GitHub; external links
 * and in-page anchors are kept as they are.
 */
export function guideLink(href: string, from: string): { route: string } | { url: string } {
  if (NOT_RELATIVE.test(href)) return { url: href }
  const [, target = '', anchor = ''] = /^([^#]*)(#.*)?$/.exec(href) ?? []
  const path = resolvePath(from, target)
  if (BUNDLED.test(path)) {
    const [, , slug] = GUIDE_FILE.exec(fileName(path)) ?? []
    return { route: helpUrl(slug) + anchor }
  }
  return { url: REPO_BLOB_URL + path + anchor }
}

/** `target`, relative to the file `from`, as a path from the repository root. */
function resolvePath(from: string, target: string): string {
  const parts = from.split('/').slice(0, -1)
  for (const part of target.split('/')) {
    if (part === '..') parts.pop()
    else if (part !== '.' && part !== '') parts.push(part)
  }
  return parts.join('/')
}
