/**
 * PROTOTYPE (throwaway, branch prototype/ontology-map-d3): the floating bar that cycles a
 * page's UI variants through `?variant=`. Dev builds only, so a stray merge can't ship it.
 */
import { useEffect } from 'react'
import { ChevronLeft, ChevronRight } from 'lucide-react'
import { useSearchParams } from 'react-router'

export interface PrototypeVariant {
  key: string
  name: string
}

export function PrototypeSwitcher({ variants, param = 'variant' }: { variants: PrototypeVariant[]; param?: string }) {
  const [params, setParams] = useSearchParams()
  const current = Math.max(
    0,
    variants.findIndex((v) => v.key === params.get(param)),
  )
  const go = (step: number) => {
    const v = variants[(current + step + variants.length) % variants.length]
    setParams(
      (p) => {
        const next = new URLSearchParams(p)
        next.set(param, v.key)
        return next
      },
      { replace: true },
    )
  }

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement | null
      if (t && (t.closest('input, textarea, select, [contenteditable]') || t.isContentEditable)) return
      if (e.key === 'ArrowLeft') go(-1)
      if (e.key === 'ArrowRight') go(1)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  })

  if (!import.meta.env.DEV) return null
  const v = variants[current]
  return (
    <div className="fixed bottom-4 left-1/2 z-50 flex -translate-x-1/2 items-center gap-1 rounded-full bg-zinc-900 px-2 py-1.5 text-sm text-white shadow-xl ring-2 ring-fuchsia-500">
      <button type="button" aria-label="Previous variant" className="rounded-full p-1 hover:bg-white/15" onClick={() => go(-1)}>
        <ChevronLeft className="size-4" />
      </button>
      <span className="min-w-56 px-2 text-center font-mono text-xs">
        <span className="text-fuchsia-300">PROTOTYPE</span> {v.key} · {v.name}{' '}
        <span className="text-white/50">
          {current + 1}/{variants.length}
        </span>
      </span>
      <button type="button" aria-label="Next variant" className="rounded-full p-1 hover:bg-white/15" onClick={() => go(1)}>
        <ChevronRight className="size-4" />
      </button>
    </div>
  )
}
