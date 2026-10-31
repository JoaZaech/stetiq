import type { LucideIcon } from 'lucide-react'
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'

export interface ViewOption<M extends string> {
  value: M
  label: string
  icon: LucideIcon
}

/** A page's view toggle (Table/Chart, Table/Map...); pair it with `useViewParam()`. */
export function ViewToggle<M extends string>({
  options,
  mode,
  onChange,
}: {
  options: readonly ViewOption<M>[]
  mode: M
  onChange: (mode: M) => void
}) {
  return (
    <ToggleGroup
      type="single"
      variant="outline"
      size="sm"
      spacing={0}
      aria-label="View"
      value={mode}
      // Radix sends '' when the active item is clicked again: keep the current mode.
      onValueChange={(value) => value && onChange(value as M)}
    >
      {options.map(({ value, label, icon: Icon }) => (
        <ToggleGroupItem key={value} value={value}>
          <Icon aria-hidden />
          {label}
        </ToggleGroupItem>
      ))}
    </ToggleGroup>
  )
}
