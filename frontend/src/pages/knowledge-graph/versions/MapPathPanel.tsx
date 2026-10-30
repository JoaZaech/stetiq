import { X } from 'lucide-react'
import { Button } from '@/components/ui/button'
import type { MapPath } from './ontology-map-paths'

/**
 * The shortest paths between two selected classes, each as the classes it passes, with
 * the superclasses a step inherits its Pattern from; or, when there is none, that no path
 * connects them.
 */
export function MapPathPanel({
  from,
  to,
  paths,
  onClose,
}: {
  from: string
  to: string
  paths: MapPath[]
  onClose: () => void
}) {
  const steps = paths[0]?.steps.length ?? 0

  return (
    <aside aria-label="Path" className="w-80 shrink-0 space-y-4 overflow-y-auto border-l bg-background p-4 text-sm">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="text-xs text-muted-foreground">Shortest path</div>
          <h3 className="font-semibold break-words">
            {from} to {to}
          </h3>
        </div>
        <Button variant="ghost" size="icon-sm" aria-label="Close path" onClick={onClose}>
          <X aria-hidden />
        </Button>
      </div>

      {paths.length === 0 ? (
        <p className="text-muted-foreground">
          No path connects {from} and {to}: no Pattern relates them, directly or through other classes, nor
          through one a superclass declares.
        </p>
      ) : (
        <>
          <p className="text-muted-foreground">
            {paths.length === 1 ? '1 path' : `${paths.length} paths`} of {steps === 1 ? '1 step' : `${steps} steps`},
            relations taken either way round.
          </p>
          <ol className="space-y-3">
            {paths.map((p) => (
              <li key={p.classes.join()} className="space-y-1">
                <div className="font-medium">{p.classes.join(' → ')}</div>
                {p.steps.map(
                  (s, i) =>
                    s.ancestors.length > 0 && (
                      <div key={i} className="text-xs text-muted-foreground">
                        {p.classes[i]} – {p.classes[i + 1]}: inherited from {s.ancestors.join(', ')}
                      </div>
                    ),
                )}
              </li>
            ))}
          </ol>
        </>
      )}
    </aside>
  )
}
