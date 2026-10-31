/**
 * How big the Map draws a class's node and a link's label. Their text is monospace, so
 * its width follows from its length, and the Map draws each at exactly the size placed
 * here, so what is laid out is what is drawn.
 */
import type { AttributeChange, OntologyComparison } from '../comparison/ontology-map-comparison'

export interface Size {
  width: number
  height: number
}

/** The least size of a class's node: a class grows from it to fit its name and its changed attributes. */
export const NODE_SIZE = { width: 160, height: 40 } as const

/** The size of the Map's monospace text: link labels and a class's changed attributes. */
export const MONOSPACE_FONT_SIZE = 11
/** The size of a class's name, also monospace: legible at the Map's least zoom. */
export const CLASS_NAME_FONT_SIZE = 14
/** Monospace advance per character, as a share of the font size. */
const CHAR_WIDTH = 0.62

/** How wide `text` is in monospace at `fontSize`, by default the Map's monospace text. */
const textWidth = (text: string, fontSize = MONOSPACE_FONT_SIZE) => Math.ceil(text.length * fontSize * CHAR_WIDTH)

/**
 * The width a class's node keeps around its name: its padding and border either side
 * (a selected class's border is thicker), and a documentation-only change's dot after it.
 */
const NAME_PADDING = 32

const LABEL_PADDING = 8
const LABEL_HEIGHT = 18

/** The pill a relation's label is drawn on. */
export const labelSize = (relation: string): Size => ({
  width: textWidth(relation) + 2 * LABEL_PADDING,
  height: LABEL_HEIGHT,
})

/** A changed attribute's marker, diff-style. */
export const ATTRIBUTE_MARKER: Record<AttributeChange['kind'], string> = { removed: '−', added: '+', modified: '~' }

/** A changed attribute's line on its class: marker, name, and a modified one's changes. */
export const attributeLine = (a: AttributeChange) =>
  [ATTRIBUTE_MARKER[a.kind], a.name, ...(a.details.length > 0 ? [a.details.join('; ')] : [])].join(' ')

/** One attribute line's height. */
export const ATTRIBUTE_LINE_HEIGHT = 16
/** The widest a class grows to fit its lines (longer ones truncate, its name never), and its box's padding. */
const EXPANDED_MAX_WIDTH = 320
const EXPANDED_PADDING = 16

/**
 * A class's node size: `NODE_SIZE`, grown to fit its whole name (`label`) on one line,
 * and to list its changed attributes.
 */
export function classNodeSize(label: string, attributes: AttributeChange[] = []): Size {
  const named = Math.max(NODE_SIZE.width, textWidth(label, CLASS_NAME_FONT_SIZE) + NAME_PADDING)
  if (attributes.length === 0) return named === NODE_SIZE.width ? NODE_SIZE : { ...NODE_SIZE, width: named }
  const longest = Math.max(...attributes.map((a) => textWidth(attributeLine(a))))
  return {
    width: Math.max(named, Math.min(EXPANDED_MAX_WIDTH, longest + EXPANDED_PADDING)),
    height: NODE_SIZE.height + attributes.length * ATTRIBUTE_LINE_HEIGHT + EXPANDED_PADDING / 2,
  }
}

/**
 * Each class's node size, by label (`labels`): grown to fit its name and, in a
 * comparison, to list its changed attributes (its `changes.attributes`).
 */
export function classSizes(
  labels: string[],
  changedAttributes: OntologyComparison['changes']['attributes'] = {},
): Record<string, Size> {
  return Object.fromEntries(labels.map((label) => [label, classNodeSize(label, changedAttributes[label])]))
}
