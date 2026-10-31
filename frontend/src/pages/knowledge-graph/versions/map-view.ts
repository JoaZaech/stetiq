import { useState } from 'react'
import { Network, Table2 } from 'lucide-react'
import type { ViewOption } from '@/components/ViewToggle'

/** An Ontology, or a comparison of two, drawn as a Map or listed as tables. */
export type MapView = 'map' | 'table'

/** Map first: the default, with `?view=` absent. */
export const MAP_VIEWS: readonly [MapView, ...MapView[]] = ['map', 'table']

/** The Table / Map toggle of the Ontology tab, the Changes tab and the Compare page. */
export const MAP_VIEW_OPTIONS: readonly ViewOption<MapView>[] = [
  { value: 'table', label: 'Table', icon: Table2 },
  { value: 'map', label: 'Map', icon: Network },
]

/**
 * How tall the Map is: down to near the window's bottom from where it sits under the
 * page's header, tabs and toolbar (about 18rem), so the readable zoom rarely leaves a
 * small Ontology to pan; never less than 32rem. Its loading placeholder is as tall.
 */
export const MAP_HEIGHT = 'h-[max(32rem,calc(100dvh-18rem))]'

/**
 * Where a Map draws its filters: an element in the page's header row, beside the Table /
 * Map toggle, so nothing overlays the top of the canvas. Set the element's `ref` to the
 * setter and pass the element to the Map as `filtersIn`.
 */
export function useMapFiltersSlot() {
  return useState<HTMLElement | null>(null)
}
