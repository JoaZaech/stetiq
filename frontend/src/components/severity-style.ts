/**
 * How severity is drawn wherever a Diff is shown (the comparison, the Diff view and its
 * badges): the Diff colours, which nothing else uses.
 */
import { type Classification, isCosmetic } from '@/api/ontology-diff'

/**
 * Severity's channel: the Diff colours as Tailwind classes, for each part of a mark.
 * Cosmetic has no Diff colour: it is drawn neutral, and keyed by `CosmeticDot`, not a swatch.
 */
export const SEVERITY: Record<'border' | 'fill' | 'ring' | 'text', Record<Classification, string>> & {
  swatch: Record<Exclude<Classification, 'cosmetic'>, string>
} = {
  border: {
    cosmetic: 'border-muted-foreground',
    additive: 'border-diff-additive',
    deprecating: 'border-diff-deprecating',
    breaking: 'border-diff-breaking',
  },
  fill: {
    cosmetic: 'bg-muted',
    additive: 'bg-diff-additive/15',
    deprecating: 'bg-diff-deprecating/15',
    breaking: 'bg-diff-breaking/15',
  },
  ring: {
    cosmetic: 'ring-muted-foreground',
    additive: 'ring-diff-additive',
    deprecating: 'ring-diff-deprecating',
    breaking: 'ring-diff-breaking',
  },
  text: {
    cosmetic: 'text-muted-foreground',
    additive: 'text-diff-additive',
    deprecating: 'text-diff-deprecating',
    breaking: 'text-diff-breaking',
  },
  /** A key's solid swatch (`SeveritySwatch`). */
  swatch: {
    additive: 'bg-diff-additive',
    deprecating: 'bg-diff-deprecating',
    breaking: 'bg-diff-breaking',
  },
}

/** A severity's Diff colour as an SVG stroke, or null for none (cosmetic has none). */
export const severityStroke = (severity: Classification | null) =>
  severity && !isCosmetic(severity) ? `var(--diff-${severity})` : null
