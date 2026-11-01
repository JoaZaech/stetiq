import { describe, expect, it } from 'vitest'
import { conceptKindLabel } from './concept-kind'

describe('conceptKindLabel', () => {
  it("names each wire kind in the glossary's words", () => {
    expect(conceptKindLabel('node_type')).toBe('Class')
    expect(conceptKindLabel('relationship_type')).toBe('Relation')
    expect(conceptKindLabel('property')).toBe('Attribute')
    expect(conceptKindLabel('vocabulary')).toBe('Vocabulary')
  })

  it('keeps a pattern, which is not a Concept, in lower case', () => {
    expect(conceptKindLabel('pattern')).toBe('pattern')
  })

  it("names the Map's and the Table's kinds the same way", () => {
    expect(conceptKindLabel('class')).toBe('Class')
    expect(conceptKindLabel('relation')).toBe('Relation')
    expect(conceptKindLabel('attribute')).toBe('Attribute')
  })
})
