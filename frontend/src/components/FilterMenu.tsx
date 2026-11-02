import { ChevronDown } from 'lucide-react'
import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'

/**
 * A toolbar filter as a dropdown, `Kind: All ▾`: one value of `options`, or `''` for all.
 * Each option may carry a count, shown beside it.
 */
export function FilterMenu({
  label,
  value,
  options,
  onChange,
  allLabel = 'All',
}: {
  label: string
  value: string
  options: readonly (readonly [value: string, count?: number])[]
  onChange: (value: string) => void
  allLabel?: string
}) {
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="outline" size="sm" aria-label={`${label}: ${value || allLabel}`}>
          <span className="text-muted-foreground">{label}:</span> {value || allLabel}
          <ChevronDown aria-hidden />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" className="max-h-96 min-w-48 overflow-y-auto">
        <DropdownMenuRadioGroup value={value} onValueChange={onChange}>
          <DropdownMenuRadioItem value="">{allLabel}</DropdownMenuRadioItem>
          {options.map(([option, count]) => (
            <DropdownMenuRadioItem key={option} value={option}>
              <span className="flex-1">{option}</span>
              {count !== undefined && <span className="ml-3 text-xs text-muted-foreground tabular-nums">{count}</span>}
            </DropdownMenuRadioItem>
          ))}
        </DropdownMenuRadioGroup>
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
