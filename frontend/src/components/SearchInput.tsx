import { Search } from 'lucide-react'
import { Input } from '@/components/ui/input'
import { cn } from '@/lib/utils'

/**
 * A search box with a magnifier, named `label` (also its placeholder unless given one).
 * `className` sizes it, by default to a fixed width that shrinks to fit.
 */
export function SearchInput({
  label,
  placeholder = label,
  value,
  onChange,
  className,
}: {
  label: string
  placeholder?: string
  value: string
  onChange: (value: string) => void
  className?: string
}) {
  return (
    <div className={cn('relative w-72 max-w-full', className)}>
      <Search aria-hidden className="absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-muted-foreground" />
      <Input
        type="search"
        aria-label={label}
        placeholder={placeholder}
        className="pl-8"
        value={value}
        onChange={(e) => onChange(e.target.value)}
      />
    </div>
  )
}
