/** Where the Map centres: on the selection it opened on, or on a search result picked. */
import { type ConceptSelection, formatSelection } from '../concept-selection'
import type { OntologyMap } from './ontology-map'
import type { MapSelection } from './ontology-map-focus'
import type { Point } from './ontology-map-layout'
import { NODE_SIZE, type Size } from './ontology-map-sizes'

/**
 * The point to centre the Map on for `selection`: a class's centre, or the midpoint of
 * a link's two classes, each at its size (`sizes`, else `NODE_SIZE`). Null for any other
 * selection, or one the Map does not have.
 */
export function centreOf(
  map: OntologyMap,
  positions: Record<string, Point>,
  sizes: Record<string, Size>,
  selection: MapSelection | null,
): Point | null {
  const classCentre = (label: string): Point | null => {
    const at = positions[label]
    if (!at) return null
    const { width, height } = sizes[label] ?? NODE_SIZE
    return { x: at.x + width / 2, y: at.y + height / 2 }
  }
  if (selection?.kind === 'class') return classCentre(selection.label)
  if (selection?.kind !== 'link') return null
  const link = map.links.find((l) => l.id === selection.id)
  const [a, b] = link ? [classCentre(link.source), classCentre(link.target)] : []
  return a && b ? { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 } : null
}

/**
 * What the Map stays centred on: `selection`, the Map's form of the page's `selected`,
 * while `selected` is still `located` (a `?select=` value: the selection the Map opened
 * on, or the search result last picked). Selecting anything else on the Map stops it.
 */
export const locatedSelection = (
  located: string | null,
  selected: ConceptSelection | null,
  selection: MapSelection | null,
): MapSelection | null => (selected && located === formatSelection(selected) ? selection : null)
