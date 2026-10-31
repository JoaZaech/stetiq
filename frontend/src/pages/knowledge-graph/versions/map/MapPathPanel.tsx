import { formatCount } from '@/lib/format'
import { MapSidePanel, type MapPanelNav } from './MapSidePanel'
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
  nav,
}: {
  from: string
  to: string
  paths: MapPath[]
  nav: MapPanelNav
}) {
  const steps = paths[0]?.steps.length ?? 0

  return (
    <MapSidePanel label="Path" kind="Shortest path" title={`${from} to ${to}`} nav={nav}>
      {paths.length === 0 ? (
        <p className="text-muted-foreground">
          No path connects {from} and {to}: no Pattern relates them, directly or through other classes, nor
          through one a superclass declares.
        </p>
      ) : (
        <>
          <p className="text-muted-foreground">
            {formatCount(paths.length, 'path')} of {formatCount(steps, 'step')},
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
    </MapSidePanel>
  )
}
