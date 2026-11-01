import { describe, expect, it } from 'vitest'
import { STATUS_TONES } from './status-tones'

describe('STATUS_TONES', () => {
  it('gives every tone its own icon, so no status relies on colour alone', () => {
    const icons = Object.values(STATUS_TONES).map((tone) => tone.Icon)
    expect(new Set(icons).size).toBe(icons.length)
  })

  it('draws warning in the status amber and neutral in the muted grey', () => {
    expect(STATUS_TONES.warning.className).toBe('text-warning')
    expect(STATUS_TONES.neutral.className).toBe('text-muted-foreground')
  })
})
