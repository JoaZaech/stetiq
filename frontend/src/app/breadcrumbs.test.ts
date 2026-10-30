import { describe, expect, it } from 'vitest'
import { breadcrumbs } from './breadcrumbs'

describe('breadcrumbs', () => {
  it('lists every matched route that names a crumb, outermost first', () => {
    const matches = [
      { pathname: '/', params: {}, handle: undefined },
      { pathname: '/kg', params: {}, handle: { crumb: () => 'Knowledge Graphs' } },
      {
        pathname: '/kg/support',
        params: { name: 'support' },
        handle: { crumb: (p: Record<string, string | undefined>) => p.name ?? '' },
      },
      { pathname: '/kg/support/versions', params: { name: 'support' }, handle: {} },
    ]

    expect(breadcrumbs(matches)).toEqual([
      { label: 'Knowledge Graphs', to: '/kg' },
      { label: 'support', to: '/kg/support' },
    ])
  })

  it('is empty when no route names a crumb', () => {
    expect(breadcrumbs([{ pathname: '/', params: {}, handle: null }])).toEqual([])
  })
})
