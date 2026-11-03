/** PROTOTYPE (branch prototype/ontology-map-d3): the variants `?variant=` picks between. */
import type { ComponentType } from 'react'
import type { Ontology } from '@/api/ontology-versions'
import type { SchemaView } from './schema-view.prototype'
import { anchoredSizeOf, cardSizeOf } from './sizes.prototype'
import type { Point, Size } from './stable-layout.prototype'
import { VariantAnchored } from './VariantAnchored.prototype'
import { VariantCards } from './VariantCards.prototype'
import { VariantMatrix } from './VariantMatrix.prototype'

export interface VariantProps {
  view: SchemaView
  /** Every version's Ontology, oldest first: the layout's whole history. */
  history: Ontology[]
  positions: Map<string, Point>
  sizeOf: (label: string) => Size
  query: string
  selected: string | null
  onSelect: (label: string | null) => void
}

interface VariantDef {
  name: string
  sizeOf: (history: Ontology[]) => (label: string) => Size
  Component: ComponentType<VariantProps>
}

export const PROTOTYPE_VARIANTS: Record<string, VariantDef> = {
  A: { name: 'Anchored map', sizeOf: anchoredSizeOf, Component: VariantAnchored },
  B: { name: 'Schema cards', sizeOf: cardSizeOf, Component: VariantCards },
  // The matrix has no positions of its own: it orders rows by the anchored map's layout.
  C: { name: 'Matrix', sizeOf: anchoredSizeOf, Component: VariantMatrix },
}

