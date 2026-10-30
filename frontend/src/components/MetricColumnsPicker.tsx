import { Columns3 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuCheckboxItem,
  DropdownMenuContent,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'

interface MetricColumnsPickerProps {
  /** Every metric that can be shown, in display order. */
  metrics: readonly string[]
  /** The metrics shown as columns (e.g. from `useMetricColumns()`). */
  selected: readonly string[]
  onChange: (selected: string[]) => void
  /** The menu's heading, e.g. "Evaluator metrics". */
  heading?: string
}

/** A "Metric columns" menu of checkboxes, one per metric. Stays open while ticking. */
export function MetricColumnsPicker({ metrics, selected, onChange, heading = 'Metrics' }: MetricColumnsPickerProps) {
  const toggle = (metric: string, checked: boolean) =>
    onChange(checked ? metrics.filter((m) => m === metric || selected.includes(m)) : selected.filter((m) => m !== metric))
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="outline" size="sm" disabled={metrics.length === 0}>
          <Columns3 aria-hidden />
          Metric columns
          {selected.length > 0 && <span className="text-muted-foreground tabular-nums">{selected.length}</span>}
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="max-h-96 w-80">
        <DropdownMenuLabel>{heading}</DropdownMenuLabel>
        <DropdownMenuSeparator />
        {metrics.map((metric) => (
          <DropdownMenuCheckboxItem
            key={metric}
            checked={selected.includes(metric)}
            onCheckedChange={(checked) => toggle(metric, checked)}
            onSelect={(event) => event.preventDefault()}
          >
            <span className="truncate" title={metric}>
              {metric}
            </span>
          </DropdownMenuCheckboxItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
