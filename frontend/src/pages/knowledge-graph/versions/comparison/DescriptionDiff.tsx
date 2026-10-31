import { Fragment, useMemo } from 'react'
import { type WordDiffPart, wordDiff } from '@/lib/word-diff'
import type { DescriptionChange } from './ontology-map-comparison'

/**
 * A documentation-only change's description Before and After, stacked, its changed words
 * marked: removed ones struck through in Before, added ones underlined in After.
 */
export function DescriptionDiff({ change: { before, after } }: { change: DescriptionChange }) {
  const parts = useMemo(() => wordDiff(before, after), [before, after])
  const sides: [string, WordDiffPart[]][] = [
    ['Before', parts.filter((p) => p.kind !== 'added')],
    ['After', parts.filter((p) => p.kind !== 'removed')],
  ]
  return (
    <div className="space-y-1 text-xs">
      {sides.map(([label, words]) => (
        <div key={label}>
          <div className="font-medium text-muted-foreground">{label}</div>
          {words.length === 0 ? (
            <p className="text-muted-foreground italic">No description.</p>
          ) : (
            <p role="group" aria-label={label}>
              {words.map((w, i) => (
                <Fragment key={i}>
                  {i > 0 && ' '}
                  {w.kind === 'removed' ? (
                    <del className="line-through">{w.text}</del>
                  ) : w.kind === 'added' ? (
                    <ins className="underline underline-offset-2">{w.text}</ins>
                  ) : (
                    w.text
                  )}
                </Fragment>
              ))}
            </p>
          )}
        </div>
      ))}
    </div>
  )
}
