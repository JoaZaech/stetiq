import { describe, expect, it } from 'vitest'
import { guideLink, guidePages } from './guide-index'

describe('guidePages', () => {
  it('orders pages by number prefix, with the slug from the filename and the title from the first heading', () => {
    const pages = guidePages({
      '../../docs/guide/10-web-ui.md': '# Using the web UI\n\nTour.',
      '../../docs/guide/02-concepts.md': 'Intro line\n\n# Concepts\n\n## Drift\n\n# Later heading',
      '../../docs/guide/01-getting-started.md': '# Getting started\n\nInstall.',
    })

    expect(pages.map(({ slug, title }) => ({ slug, title }))).toEqual([
      { slug: 'getting-started', title: 'Getting started' },
      { slug: 'concepts', title: 'Concepts' },
      { slug: 'web-ui', title: 'Using the web UI' },
    ])
    expect(pages[0].markdown).toBe('# Getting started\n\nInstall.')
    expect(pages[0].path).toBe('docs/guide/01-getting-started.md')
  })

  it('puts files without a number prefix last, by filename, and titles a page without a heading by its slug', () => {
    const pages = guidePages({
      'guide/zeta.md': '# Zeta',
      'guide/alpha.md': 'No heading here.\n\n## Only a subheading',
      'guide/03-cli.md': '# CLI',
    })

    expect(pages.map(({ slug, title }) => ({ slug, title }))).toEqual([
      { slug: 'cli', title: 'CLI' },
      { slug: 'alpha', title: 'alpha' },
      { slug: 'zeta', title: 'Zeta' },
    ])
  })
})

describe('guideLink', () => {
  const FROM_GUIDE = 'docs/guide/01-getting-started.md'
  const FROM_VISION = 'docs/vision.md'

  it('turns a relative link to another guide file into its in-app Help route', () => {
    expect(guideLink('./04-cli.md', FROM_GUIDE)).toEqual({ route: '/help/cli' })
    expect(guideLink('02-concepts.md', FROM_GUIDE)).toEqual({ route: '/help/concepts' })
    expect(guideLink('notes.md', FROM_GUIDE)).toEqual({ route: '/help/notes' })
  })

  it('keeps the anchor of a relative guide link', () => {
    expect(guideLink('./04-cli.md#tracking-uri', FROM_GUIDE)).toEqual({ route: '/help/cli#tracking-uri' })
  })

  it('routes links between the guide and the vision page, which is bundled too', () => {
    expect(guideLink('../vision.md#connector', FROM_GUIDE)).toEqual({ route: '/help/vision#connector' })
    expect(guideLink('guide/04-cli.md', FROM_VISION)).toEqual({ route: '/help/cli' })
  })

  it('points links to other files in the repository at GitHub, since the app does not bundle them', () => {
    expect(guideLink('../GLOSSARY.md', FROM_VISION)).toEqual({
      url: 'https://github.com/JoaZaech/stetiq/blob/main/GLOSSARY.md',
    })
    expect(guideLink('specs/consumer-connector.md#events', FROM_VISION)).toEqual({
      url: 'https://github.com/JoaZaech/stetiq/blob/main/docs/specs/consumer-connector.md#events',
    })
    expect(guideLink('../architecture.md', FROM_GUIDE)).toEqual({
      url: 'https://github.com/JoaZaech/stetiq/blob/main/docs/architecture.md',
    })
  })

  it('leaves external links and in-page anchors alone', () => {
    const github = 'https://github.com/JoaZaech/stetiq/blob/main/04-cli.md'
    expect(guideLink(github, FROM_GUIDE)).toEqual({ url: github })
    expect(guideLink('mailto:someone@example.com', FROM_GUIDE)).toEqual({ url: 'mailto:someone@example.com' })
    expect(guideLink('#install', FROM_GUIDE)).toEqual({ url: '#install' })
  })
})
