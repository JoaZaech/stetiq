import { type ReactElement, useState } from 'react'
import { Network, Table2 } from 'lucide-react'
import { type ViewOption, ViewToggle } from '@/components/ViewToggle'
import type { MapView } from './map-view'

/** The Table / Map toggle's options. */
const MAP_VIEW_OPTIONS: readonly ViewOption<MapView>[] = [
  { value: 'table', label: 'Table', icon: Table2 },
  { value: 'map', label: 'Map', icon: Network },
]

/**
 * The header row's controls of the Ontology tab, the Changes tab and the Compare page:
 * on the Map, the slot its filters go in, then the Table / Map toggle. `controls` goes in
 * the header row; `filtersIn`, the slot, goes to the Map as its `filtersIn`, so nothing
 * overlays the top of the canvas.
 */
export function useMapViewControls(
  view: MapView,
  onViewChange: (view: MapView) => void,
): { controls: ReactElement; filtersIn: HTMLElement | null } {
  const [filtersIn, setFiltersIn] = useState<HTMLElement | null>(null)
  const controls = (
    <div className="flex items-center gap-4">
      {view === 'map' && <div ref={setFiltersIn} className="flex items-center gap-4" />}
      <ViewToggle options={MAP_VIEW_OPTIONS} mode={view} onChange={onViewChange} />
    </div>
  )
  return { controls, filtersIn }
}
