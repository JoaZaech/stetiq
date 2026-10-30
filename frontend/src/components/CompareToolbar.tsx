import type { ReactNode } from 'react'
import { GitCompare } from 'lucide-react'
import { Button } from '@/components/ui/button'

interface CompareToolbarProps {
  /** How many rows are selected. */
  selected: number
  /** `two`: exactly two rows (a two-way compare); `many`: two or more. */
  needs: 'two' | 'many'
  /** What to select, e.g. "versions" or "runs": shown until enough rows are. */
  noun: string
  /** What Compare will show, once enough rows are selected. */
  readyHint: string
  onCompare: () => void
  /** More controls on the same row, e.g. filters (left) and a column picker (right). */
  children?: ReactNode
}

/** The row above a selectable table: "select N rows, then Compare". */
export function CompareToolbar({ selected, needs, noun, readyHint, onCompare, children }: CompareToolbarProps) {
  const ready = needs === 'two' ? selected === 2 : selected >= 2
  return (
    <div className="flex flex-wrap items-center gap-3">
      <Button size="sm" variant="outline" disabled={!ready} onClick={onCompare}>
        <GitCompare aria-hidden />
        Compare
      </Button>
      <span className="text-xs text-muted-foreground">
        {ready ? readyHint : `Select ${needs === 'two' ? 'two' : 'two or more'} ${noun} to compare`}
      </span>
      {children}
    </div>
  )
}
