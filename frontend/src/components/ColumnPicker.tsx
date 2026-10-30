import { Fragment } from 'react'
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

export interface ColumnPickerGroup {
  /** e.g. "Params", "Metrics" */
  label: string
  /** The optional columns of this group: a table column id and the name shown. */
  columns: readonly { id: string; label: string }[]
}

interface ColumnPickerProps {
  groups: readonly ColumnPickerGroup[]
  /** Ids of the columns shown now. */
  visible: ReadonlySet<string>
  onToggle: (id: string, visible: boolean) => void
}

/**
 * A "Columns" menu that shows or hides a table's optional columns (e.g. param and
 * metric columns), one checkbox per column. It holds no state: pair it with the
 * table's column visibility, e.g. kept in the URL so the view can be shared.
 */
export function ColumnPicker({ groups, visible, onToggle }: ColumnPickerProps) {
  const shown = groups.filter((g) => g.columns.length > 0)
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="outline" size="sm">
          <Columns3 aria-hidden />
          Columns
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="max-h-96 min-w-48 overflow-y-auto">
        {shown.length === 0 && (
          <DropdownMenuLabel className="font-normal text-muted-foreground">
            No columns to add
          </DropdownMenuLabel>
        )}
        {shown.map((group, i) => (
          <Fragment key={group.label}>
            {i > 0 && <DropdownMenuSeparator />}
            <DropdownMenuLabel>{group.label}</DropdownMenuLabel>
            {group.columns.map((column) => (
              <DropdownMenuCheckboxItem
                key={column.id}
                checked={visible.has(column.id)}
                onCheckedChange={(checked) => onToggle(column.id, checked)}
                // Keep the menu open to pick several columns in a row.
                onSelect={(event) => event.preventDefault()}
              >
                {column.label}
              </DropdownMenuCheckboxItem>
            ))}
          </Fragment>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
