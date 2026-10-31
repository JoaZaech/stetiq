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

/** A class's node is this size unless the Map gives it another, as a comparison does a class it expands. */
export const NODE_SIZE = { width: 160, height: 40 } as const

/** The size of the Map's monospace text: link labels and a class's changed attributes. */
export const MONOSPACE_FONT_SIZE = 11
/** Monospace advance per character, as a share of the font size. */
const CHAR_WIDTH = 0.62

/** How wide `text` is in the Map's monospace text. */
const textWidth = (text: string) => Math.ceil(text.length * MONOSPACE_FONT_SIZE * CHAR_WIDTH)

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
/** The widest a class grows to fit its lines (longer ones truncate), and its box's padding. */
const EXPANDED_MAX_WIDTH = 320
const EXPANDED_PADDING = 16

/** A class's node size: `NODE_SIZE`, grown to list its changed attributes. */
export function classNodeSize(attributes: AttributeChange[] = []): Size {
  if (attributes.length === 0) return NODE_SIZE
  const longest = Math.max(...attributes.map((a) => textWidth(attributeLine(a))))
  return {
    width: Math.min(EXPANDED_MAX_WIDTH, Math.max(NODE_SIZE.width, longest + EXPANDED_PADDING)),
    height: NODE_SIZE.height + attributes.length * ATTRIBUTE_LINE_HEIGHT + EXPANDED_PADDING / 2,
  }
}

/**
 * The classes drawn at other than `NODE_SIZE`, by label: in a comparison, each class
 * with changed attributes (its `changes.attributes`), grown to list them.
 */
export function classSizes(
  changedAttributes: OntologyComparison['changes']['attributes'] = {},
): Record<string, Size> {
  return Object.fromEntries(
    Object.entries(changedAttributes)
      .filter(([, attributes]) => attributes.length > 0)
      .map(([label, attributes]) => [label, classNodeSize(attributes)]),
  )
}
