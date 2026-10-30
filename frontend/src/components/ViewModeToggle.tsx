import { ChartLine, Table2 } from 'lucide-react'
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'
import type { ViewMode } from '@/lib/metric-view-params'

/** The Table/Chart toggle of a list page; pair it with `useViewMode()`. */
export function ViewModeToggle({ mode, onChange }: { mode: ViewMode; onChange: (mode: ViewMode) => void }) {
  return (
    <ToggleGroup
      type="single"
      variant="outline"
      size="sm"
      spacing={0}
      aria-label="View"
      value={mode}
      // Radix sends '' when the active item is clicked again: keep the current mode.
      onValueChange={(value) => value && onChange(value as ViewMode)}
    >
      <ToggleGroupItem value="table">
        <Table2 aria-hidden />
        Table
      </ToggleGroupItem>
      <ToggleGroupItem value="chart">
        <ChartLine aria-hidden />
        Chart
      </ToggleGroupItem>
    </ToggleGroup>
  )
}
