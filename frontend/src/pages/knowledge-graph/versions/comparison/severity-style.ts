/** How severity is drawn in a comparison: the Diff colours, which nothing else uses. */
import type { Classification } from '@/api/ontology-diff'

/** Severity's channel: the Diff colours as Tailwind classes, for each part of a mark. */
export const SEVERITY: Record<'border' | 'fill' | 'ring' | 'text', Record<Classification, string>> = {
  border: {
    additive: 'border-diff-additive',
    deprecating: 'border-diff-deprecating',
    breaking: 'border-diff-breaking',
  },
  fill: {
    additive: 'bg-diff-additive/15',
    deprecating: 'bg-diff-deprecating/15',
    breaking: 'bg-diff-breaking/15',
  },
  ring: {
    additive: 'ring-diff-additive',
    deprecating: 'ring-diff-deprecating',
    breaking: 'ring-diff-breaking',
  },
  text: {
    additive: 'text-diff-additive',
    deprecating: 'text-diff-deprecating',
    breaking: 'text-diff-breaking',
  },
}

/** A severity's Diff colour as an SVG stroke, or null for none. */
export const severityStroke = (severity: Classification | null) => severity && `var(--diff-${severity})`
