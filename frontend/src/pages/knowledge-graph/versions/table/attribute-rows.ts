import type { Ontology } from '@/api/ontology-versions'
import { type ClassOrRelation, conceptTables, constraintsOn, superclassChain } from '../concepts'
import { type DetailProperty, detailsOf } from '../map/ontology-map-focus'

/** An attribute as the Attributes grid lists it: one row per attribute a class or relation has. */
export interface AttributeGridRow {
  /** `<owner>.<name>`, unique in the grid. */
  id: string
  /** The class or relation that has it, by declaring or inheriting it. */
  owner: string
  ownerKind: ClassOrRelation['kind']
  /** The owner's superclass; classes only. */
  ownerParent?: string
  name: string
  type: string
  required: boolean
  /** Whether a uniqueness constraint covers it, on the owner or the ancestor that declares it; classes only. */
  unique: boolean
  /** The ancestor class that declares it, when the owner inherits it; absent when its own. */
  inheritedFrom?: string
  description?: string
}

/**
 * Every attribute of an Ontology, by owner: each class in hierarchy order with its own
 * attributes, then those it inherits along its superclass chain (as `detailsOf` lists
 * them), then each relation's.
 */
export function attributeRows(ontology: Ontology): AttributeGridRow[] {
  // A uniqueness constraint covers an attribute on the class it is declared on and on
  // every subclass: on the owner or any class up its chain, the declaring one included.
  const unique = (owner: string, name: string) =>
    superclassChain(ontology, owner).some((c) =>
      constraintsOn(ontology, c.label, name).some((k) => k.type === 'UNIQUENESS'),
    )
  const row = (
    owner: string,
    ownerKind: AttributeGridRow['ownerKind'],
    ownerParent: string | undefined,
    p: DetailProperty,
  ): AttributeGridRow => ({
    id: `${owner}.${p.name}`,
    owner,
    ownerKind,
    ownerParent,
    name: p.name,
    type: p.type,
    required: p.required,
    unique: ownerKind === 'class' && unique(owner, p.name),
    inheritedFrom: p.inheritedFrom,
    description: p.description,
  })

  const classes = conceptTables(ontology).classes.flatMap((c) => {
    const details = detailsOf(ontology, { kind: 'class', label: c.label })
    return details?.kind === 'class' ? details.properties.map((p) => row(c.label, 'class', c.parent, p)) : []
  })
  const relations = ontology.relationship_types.flatMap((r) =>
    (r.properties ?? []).map((p) =>
      row(r.label, 'relation', undefined, {
        name: p.name,
        type: p.type,
        description: p.description,
        required: p.required ?? false,
      }),
    ),
  )
  return [...classes, ...relations]
}
