/**
 * PROTOTYPE (throwaway, branch prototype/ontology-map-d3).
 *
 * Question: what should the Ontology Map look like once it is drawn with d3, so it is
 * more concise, more accurate and easier to read, with one layout shared by every
 * Ontology Version of the Knowledge Graph?
 *
 * Three variants of the Ontology tab's Map, switchable via `?variant=` (A, B, C; absent or
 * `current` is today's React Flow Map), on the existing `/kg/:name/versions/:n/ontology`
 * route. Extra prototype params: `?layout=union` (default anchored), `?scale=large`
 * (a synthetic 5-version, ~80-class Knowledge Graph instead of the real one).
 */
import { useMemo, useState } from 'react'
import { useSearchParams } from 'react-router'
import { useOntologyVersions, type OntologyVersion } from '@/api/ontology-versions'
import { cn } from '@/lib/utils'
import { MAP_HEIGHT } from '../map-view'
import { useKnowledgeGraphName } from '../../params'
import { schemaView, syntheticVersions, type SchemaView } from './schema-view.prototype'
import { stableLayout, type LayoutMode } from './stable-layout.prototype'
import { PROTOTYPE_VARIANTS } from './variants.prototype'

export function OntologyMapPrototype({ page, query }: { page: OntologyVersion; query: string }) {
  const kg = useKnowledgeGraphName()
  const real = useOntologyVersions(kg)
  const [params, setParams] = useSearchParams()
  const variantKey = params.get('variant') ?? 'A'
  const variant = PROTOTYPE_VARIANTS[variantKey] ?? PROTOTYPE_VARIANTS.A
  const mode: LayoutMode = params.get('layout') === 'union' ? 'union' : 'anchored'
  const large = params.get('scale') === 'large'
  const setParam = (key: string, value: string | null) =>
    setParams(
      (p) => {
        const next = new URLSearchParams(p)
        if (value === null) next.delete(key)
        else next.set(key, value)
        return next
      },
      { replace: true },
    )

  const series = useMemo(
    () => (large ? syntheticVersions() : (real.data ?? []).map((v) => ({ number: v.number, ontology: v.ontology }))),
    [large, real.data],
  )
  const [picked, setPicked] = useState<number | null>(null)
  const number = picked ?? (large ? series.length : page.number)
  const index = Math.max(
    0,
    series.findIndex((v) => v.number === number),
  )
  const [showChanges, setShowChanges] = useState(true)
  const [selected, setSelected] = useState<string | null>(null)

  const history = useMemo(() => series.map((v) => v.ontology), [series])
  const sizeOf = useMemo(() => variant.sizeOf(history), [variant, history])
  const positions = useMemo(() => stableLayout(history, mode, sizeOf), [history, mode, sizeOf])
  const current = series[index]?.ontology
  const previous = index > 0 ? series[index - 1].ontology : undefined
  const view = useMemo(
    () => current && schemaView(current, showChanges ? previous : undefined),
    [current, previous, showChanges],
  )

  // The state readout: would this version's classes sit elsewhere had no later version
  // been registered yet? That is what "the same layout for every version" has to survive.
  const moved = useMemo(() => {
    if (!current) return 0
    const prefix = stableLayout(history.slice(0, index + 1), mode, sizeOf)
    return current.node_types.filter((n) => {
      const [a, b] = [prefix.get(n.label), positions.get(n.label)]
      return !a || !b || Math.hypot(a.x - b.x, a.y - b.y) > 1
    }).length
  }, [current, history, index, mode, sizeOf, positions])

  if (!large && real.isPending) return <div className={cn(MAP_HEIGHT, 'animate-pulse rounded-lg border bg-muted/40')} />
  if (!view || !current) return <p className="text-sm text-muted-foreground">No versions.</p>
  const { Component } = variant
  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2 rounded-md border border-dashed border-fuchsia-500/60 bg-fuchsia-500/5 px-3 py-2 text-xs">
        <div role="group" aria-label="Version" className="flex items-center gap-1">
          <span className="mr-1 text-muted-foreground">Version</span>
          {series.map((v) => (
            <button
              key={v.number}
              type="button"
              onClick={() => setPicked(v.number)}
              className={cn(
                'rounded px-2 py-0.5 font-mono tabular-nums',
                v.number === number ? 'bg-foreground text-background' : 'hover:bg-accent',
                !large && v.number === page.number && v.number !== number && 'underline',
              )}
            >
              v{v.number}
            </button>
          ))}
        </div>
        <label className="flex items-center gap-1.5">
          <input type="checkbox" checked={showChanges} onChange={(e) => setShowChanges(e.target.checked)} />
          Changes since v{series[index - 1]?.number ?? '—'}
        </label>
        <div role="group" aria-label="Layout" className="flex items-center gap-1">
          <span className="mr-1 text-muted-foreground">Layout</span>
          {(['anchored', 'union'] as const).map((m) => (
            <button
              key={m}
              type="button"
              onClick={() => setParam('layout', m === 'anchored' ? null : m)}
              className={cn('rounded px-2 py-0.5', m === mode ? 'bg-foreground text-background' : 'hover:bg-accent')}
            >
              {m}
            </button>
          ))}
        </div>
        <label className="flex items-center gap-1.5">
          <input type="checkbox" checked={large} onChange={(e) => (setPicked(null), setParam('scale', e.target.checked ? 'large' : null))} />
          Stress test (synthetic, ~80 classes)
        </label>
        <span className="ml-auto font-mono text-muted-foreground">
          v{number} · {view.counts.classes} classes · {view.counts.patterns} patterns
          {previous && showChanges && (
            <>
              {' '}
              · <span className="text-diff-additive">+{view.counts.added}</span>{' '}
              <span className="text-diff-breaking">−{view.counts.removed}</span>
            </>
          )}{' '}
          ·{' '}
          <span className={moved === 0 ? 'text-diff-additive' : 'text-diff-breaking'}>
            {moved === 0 ? 'no class moves' : `${moved} classes move`} when later versions land
          </span>
        </span>
      </div>
      <div className={cn(MAP_HEIGHT, 'relative overflow-hidden rounded-lg border bg-background')}>
        <Component
          view={view}
          history={history}
          positions={positions}
          sizeOf={sizeOf}
          query={query}
          selected={selected && view.byLabel.has(selected) ? selected : null}
          onSelect={setSelected}
        />
        {selected && view.byLabel.has(selected) && (
          <ClassDetails view={view} label={selected} onSelect={setSelected} />
        )}
      </div>
    </div>
  )
}

/** The selected class: everything about it the Map leaves off. */
function ClassDetails({
  view,
  label,
  onSelect,
}: {
  view: SchemaView
  label: string
  onSelect: (label: string | null) => void
}) {
  const c = view.byLabel.get(label)!
  const out = view.rels.filter((r) => r.source === label)
  const inc = view.rels.filter((r) => r.target === label && r.source !== label)
  const subclasses = view.classes.filter((s) => s.parent === label)
  const link = (l: string) => (
    <button type="button" className="font-mono hover:underline" onClick={() => onSelect(l)}>
      {l}
    </button>
  )
  const statusText = (s: string) =>
    s === 'added' ? 'text-diff-additive' : s === 'removed' ? 'text-diff-breaking line-through' : ''
  return (
    <aside className="absolute top-2 right-2 bottom-2 w-80 space-y-3 overflow-y-auto rounded-lg border bg-card p-3 text-xs shadow-lg">
      <div className="flex items-start justify-between gap-2">
        <div>
          <div className={cn('font-mono text-sm font-semibold', statusText(c.status))}>{c.label}</div>
          {c.parent && <div className="text-muted-foreground">subclass of {link(c.parent)}</div>}
        </div>
        <button type="button" className="text-muted-foreground hover:text-foreground" onClick={() => onSelect(null)}>
          ✕
        </button>
      </div>
      {c.definition && <p className="text-muted-foreground">{c.definition}</p>}
      <section>
        <h3 className="mb-1 font-semibold">Attributes · {c.attributes.length + c.inherited.length}</h3>
        <table className="w-full font-mono">
          <tbody>
            {[...c.attributes.map((a) => ({ ...a, from: undefined as string | undefined })), ...c.inherited].map((a) => (
              <tr key={`${a.from}.${a.name}`} className={a.from ? 'text-muted-foreground' : ''}>
                <td>
                  {a.name}
                  {a.required && <span title="required">*</span>}
                </td>
                <td className="text-right">{a.vocabulary ?? a.type}</td>
                <td className="pl-2 text-right">{a.from && <>↑ {a.from}</>}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
      {[
        ['Outgoing', out, (r: (typeof out)[number]) => r.target, '→'] as const,
        ['Incoming', inc, (r: (typeof inc)[number]) => r.source, '←'] as const,
      ].map(([title, rels, other, arrow]) => (
        <section key={title}>
          <h3 className="mb-1 font-semibold">
            {title} · {rels.length}
          </h3>
          {rels.length === 0 && <div className="text-muted-foreground">—</div>}
          {rels.map((r) => (
            <div key={r.id} className={cn('font-mono', statusText(r.status))}>
              {r.relation} {arrow} {link(other(r))}
            </div>
          ))}
        </section>
      ))}
      {subclasses.length > 0 && (
        <section>
          <h3 className="mb-1 font-semibold">Subclasses · {subclasses.length}</h3>
          <div className="flex flex-wrap gap-x-2">{subclasses.map((s) => <span key={s.label}>{link(s.label)}</span>)}</div>
        </section>
      )}
    </aside>
  )
}
