import { describe, expect, it } from 'vitest'
import { parseTheme, resolveTheme } from './theme'

describe('parseTheme', () => {
  it('keeps a stored choice', () => {
    expect(parseTheme('dark')).toBe('dark')
    expect(parseTheme('light')).toBe('light')
    expect(parseTheme('system')).toBe('system')
  })

  it('defaults to system when nothing valid is stored', () => {
    expect(parseTheme(null)).toBe('system')
    expect(parseTheme('purple')).toBe('system')
  })
})

describe('resolveTheme', () => {
  it('follows the operating system only for the system choice', () => {
    expect(resolveTheme('system', true)).toBe('dark')
    expect(resolveTheme('system', false)).toBe('light')
    expect(resolveTheme('light', true)).toBe('light')
    expect(resolveTheme('dark', false)).toBe('dark')
  })
})
