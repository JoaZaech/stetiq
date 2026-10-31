import { type Classification, isCosmetic } from '@/api/ontology-diff'
import { cn } from '@/lib/utils'
import { SEVERITY } from './severity-style'

/** A cosmetic change's mark: small, round and neutral. */
export function CosmeticDot({ className }: { className?: string }) {
  return (
    <span
      aria-hidden
      data-cosmetic-dot
      className={cn('inline-block size-1.5 shrink-0 rounded-full bg-muted-foreground', className)}
    />
  )
}

/**
 * A level's key: a square in its Diff colour, or, for cosmetic changes, which have none,
 * the neutral dot the Map draws them with.
 */
export function SeveritySwatch({ level }: { level: Classification }) {
  if (isCosmetic(level)) return <CosmeticDot className="mx-0.5" />
  return (
    <span
      aria-hidden
      data-swatch={level}
      className={cn('inline-block size-2.5 shrink-0 rounded-sm', SEVERITY.swatch[level])}
    />
  )
}
