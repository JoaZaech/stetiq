import { describe, expect, it } from 'vitest'
import { canEdit, type WhoAmI } from './whoami'

const user = (grants: WhoAmI['grants']): WhoAmI => ({ mode: 'server', user: 'ada', grants })

describe('canEdit', () => {
  it('needs an edit grant on that Knowledge Graph', () => {
    const ada = user({ support: 'edit', billing: 'read' })

    expect(canEdit(ada, 'support')).toBe(true)
    expect(canEdit(ada, 'billing')).toBe(false)
    expect(canEdit(ada, 'hr')).toBe(false)
  })

  it('takes an edit grant on * for every Knowledge Graph', () => {
    expect(canEdit(user({ '*': 'edit' }), 'hr')).toBe(true)
    expect(canEdit(user({ '*': 'read', hr: 'edit' }), 'hr')).toBe(true)
    expect(canEdit(user({ '*': 'read' }), 'hr')).toBe(false)
  })

  it('is false while who-am-I is still unknown', () => {
    expect(canEdit(undefined, 'support')).toBe(false)
  })
})
