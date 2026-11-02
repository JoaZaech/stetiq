import { Link } from 'react-router'
import { STATUS_TONES, type StatusTone } from './status-tones'
import { cn } from '@/lib/utils'

/** One tile's content; `evaluationKpis` builds the four every evaluation shares. */
export interface KpiTile {
  label: string
  value: string
  tone?: StatusTone
  hint?: string
  /** App path the tile links to. */
  to?: string
}

/**
 * A row of KPI tiles: label, a large value in its tone's colour and icon, an optional
 * hint. The same tiles in the same place on every page make an evaluation recognisable.
 */
export function KpiTiles({ tiles, label = 'Key figures', className }: { tiles: readonly KpiTile[]; label?: string; className?: string }) {
  return (
    <ul aria-label={label} className={cn('grid grid-cols-2 gap-3 sm:grid-cols-4', className)}>
      {tiles.map((tile) => (
        <li key={tile.label} className="min-w-0">
          <Tile tile={tile} />
        </li>
      ))}
    </ul>
  )
}

function Tile({ tile }: { tile: KpiTile }) {
  const tone = tile.tone ? STATUS_TONES[tile.tone] : null
  const body = (
    <>
      <span className="block truncate text-xs text-muted-foreground">{tile.label}</span>
      <span className="mt-1 flex items-center gap-1.5">
        {tone && <tone.Icon aria-hidden className={`size-4 shrink-0 ${tone.className}`} />}
        <span className={cn('text-xl font-semibold tabular-nums', tone?.className, !tone && 'text-muted-foreground')}>
          {tile.value}
        </span>
      </span>
      {tile.hint && <span className="block truncate text-xs text-muted-foreground">{tile.hint}</span>}
    </>
  )
  const frame = 'block h-full rounded-lg border bg-card px-3 py-2.5'
  if (!tile.to) {
    return (
      <div className={frame} aria-label={`${tile.label}: ${tile.value}`}>
        {body}
      </div>
    )
  }
  return (
    <Link
      to={tile.to}
      aria-label={`${tile.label}: ${tile.value}`}
      className={cn(frame, 'transition-colors hover:bg-muted/50 focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none')}
    >
      {body}
    </Link>
  )
}
