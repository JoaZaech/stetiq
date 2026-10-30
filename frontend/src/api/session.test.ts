import { describe, expect, it } from 'vitest'
import { afterSignIn } from './session'

describe('afterSignIn', () => {
  it('returns to the page the user was sent from', () => {
    expect(afterSignIn('/settings')).toBe('/settings')
    expect(afterSignIn('/kg/support?tab=runs')).toBe('/kg/support?tab=runs')
  })

  it('opens the Knowledge Graph list for anything that is not a path inside the app', () => {
    expect(afterSignIn(null)).toBe('/')
    expect(afterSignIn('')).toBe('/')
    expect(afterSignIn('https://evil.example')).toBe('/')
    expect(afterSignIn('//evil.example')).toBe('/')
    expect(afterSignIn('/\\evil.example')).toBe('/')
  })
})
