import { describe, expect, it } from 'vitest'
import type { AttributeChange } from './ontology-map-comparison'
import { attributeLine, classNodeSize, classSizes, labelSize, NODE_SIZE } from './ontology-map-sizes'

const removed: AttributeChange = { name: 'wheelchairBoarding', kind: 'removed', severity: 'breaking', details: [] }
const added: AttributeChange = { name: 'wheelchair_boarding', kind: 'added', severity: 'additive', details: [] }
const modified: AttributeChange = {
  name: 'id',
  kind: 'modified',
  severity: 'breaking',
  details: ['type changed from STRING to INTEGER', 'now required'],
}

describe('labelSize', () => {
  it('grows a label’s pill with its relation’s length, at one height', () => {
    const [short, long] = [labelSize('OF'), labelSize('ESCALATED_BY_CUSTOMER')]

    expect(long.width).toBeGreaterThan(short.width)
    expect(long.height).toBe(short.height)
  })
})

describe('attributeLine', () => {
  it('writes a changed attribute diff-style, a modified one with its changes', () => {
    expect(attributeLine(removed)).toBe('− wheelchairBoarding')
    expect(attributeLine(added)).toBe('+ wheelchair_boarding')
    expect(attributeLine(modified)).toBe('~ id type changed from STRING to INTEGER; now required')
  })
})

describe('classNodeSize', () => {
  it('keeps a class without changed attributes at the node size', () => {
    expect(classNodeSize()).toEqual(NODE_SIZE)
    expect(classNodeSize([])).toEqual(NODE_SIZE)
  })

  it('grows a class one line taller per changed attribute', () => {
    const [one, two] = [classNodeSize([removed]), classNodeSize([removed, added])]

    expect(one.height).toBeGreaterThan(NODE_SIZE.height)
    expect(two.height - one.height).toBe(16)
  })

  it('widens a class to its longest line, up to a limit past which lines truncate', () => {
    expect(classNodeSize([{ ...added, name: 'x' }]).width).toBe(NODE_SIZE.width)
    expect(classNodeSize([{ ...added, name: 'wheelchair_boarding_status' }]).width).toBeGreaterThan(NODE_SIZE.width)
    expect(classNodeSize([modified]).width).toBe(320)
  })
})

describe('classSizes', () => {
  it('sizes only the classes with changed attributes', () => {
    expect(classSizes({ Stop: [removed, added], Trip: [] })).toEqual({ Stop: classNodeSize([removed, added]) })
    expect(classSizes()).toEqual({})
  })
})
