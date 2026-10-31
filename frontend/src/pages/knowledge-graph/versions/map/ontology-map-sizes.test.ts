import { describe, expect, it } from 'vitest'
import type { AttributeChange } from '../comparison/ontology-map-comparison'
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
  it('keeps a class with a short name and no changed attributes at the node size', () => {
    expect(classNodeSize('Stop')).toEqual(NODE_SIZE)
    expect(classNodeSize('Stop', [])).toEqual(NODE_SIZE)
  })

  it('widens a class to at least its whole name, at one height', () => {
    // 36 monospace characters at 14px, 0.62 of the font size each.
    const name = 'WheelchairAccessibleBoardingPlatform'
    const size = classNodeSize(name)

    expect(size.width).toBeGreaterThanOrEqual(36 * 14 * 0.62)
    expect(size.height).toBe(NODE_SIZE.height)
  })

  it('grows a class one line taller per changed attribute', () => {
    const [one, two] = [classNodeSize('Stop', [removed]), classNodeSize('Stop', [removed, added])]

    expect(one.height).toBeGreaterThan(NODE_SIZE.height)
    expect(two.height - one.height).toBe(16)
  })

  it('widens a class to its longest line, up to a limit past which lines truncate', () => {
    expect(classNodeSize('Stop', [{ ...added, name: 'x' }]).width).toBe(NODE_SIZE.width)
    expect(classNodeSize('Stop', [{ ...added, name: 'wheelchair_boarding_status' }]).width).toBeGreaterThan(
      NODE_SIZE.width,
    )
    expect(classNodeSize('Stop', [modified]).width).toBe(320)
  })

  it('never truncates a class’s name for its lines’ limit', () => {
    const name = 'WheelchairAccessibleBoardingPlatformEntrance'

    expect(classNodeSize(name, [modified]).width).toBe(classNodeSize(name).width)
  })
})

describe('classSizes', () => {
  it('sizes every class, to its name and its changed attributes', () => {
    expect(classSizes(['Stop', 'Trip'], { Stop: [removed, added], Trip: [] })).toEqual({
      Stop: classNodeSize('Stop', [removed, added]),
      Trip: NODE_SIZE,
    })
    expect(classSizes(['Stop'])).toEqual({ Stop: NODE_SIZE })
  })
})
