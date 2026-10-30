import { ChartLine, Table2 } from 'lucide-react'
import type { ViewMode } from '@/lib/metric-view-params'
import { ViewToggle, type ViewOption } from './ViewToggle'

const OPTIONS: readonly ViewOption<ViewMode>[] = [
  { value: 'table', label: 'Table', icon: Table2 },
  { value: 'chart', label: 'Chart', icon: ChartLine },
]

/** The Table/Chart toggle of a list page; pair it with `useViewMode()`. */
export function ViewModeToggle({ mode, onChange }: { mode: ViewMode; onChange: (mode: ViewMode) => void }) {
  return <ViewToggle options={OPTIONS} mode={mode} onChange={onChange} />
}
