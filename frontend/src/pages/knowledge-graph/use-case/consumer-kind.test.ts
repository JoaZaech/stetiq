import { describe, expect, it } from 'vitest'
import { consumerKindIcon } from './consumer-kind'

describe('consumerKindIcon', () => {
  it('gives each kind the glossary names its own icon, whatever its case', () => {
    expect(consumerKindIcon('application')).toBe('application')
    expect(consumerKindIcon('Agent')).toBe('agent')
    expect(consumerKindIcon(' dashboard ')).toBe('dashboard')
    expect(consumerKindIcon('team')).toBe('team')
  })

  it('gives any other kind, or none, the generic icon', () => {
    for (const kind of ['spreadsheet', 'constructor', '', undefined]) {
      expect(consumerKindIcon(kind)).toBe('other')
    }
  })
})
