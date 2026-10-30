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
  it('turns a relative link to another guide file into its in-app Help route', () => {
    expect(guideLink('./04-cli.md')).toBe('/help/cli')
    expect(guideLink('02-concepts.md')).toBe('/help/concepts')
    expect(guideLink('notes.md')).toBe('/help/notes')
  })

  it('keeps the anchor of a relative guide link', () => {
    expect(guideLink('./04-cli.md#tracking-uri')).toBe('/help/cli#tracking-uri')
  })

  it('leaves external links, in-page anchors and links outside the guide alone', () => {
    expect(guideLink('https://github.com/JoaZaech/stetiq/blob/main/04-cli.md')).toBeUndefined()
    expect(guideLink('mailto:someone@example.com')).toBeUndefined()
    expect(guideLink('#install')).toBeUndefined()
    expect(guideLink('../architecture.md')).toBeUndefined()
    expect(guideLink('./images/diagram.png')).toBeUndefined()
  })
})
