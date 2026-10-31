import type { ConceptKind, OwnerKind } from '@/api/ontology-diff'
import type { Ontology, OntologyConcept } from '@/api/ontology-versions'
import { codePointOrder } from '@/lib/compare'

/** Each kind of Concept as the Map and the Table name it. */
export const CONCEPT_NOUN = {
  node_type: 'class',
  relationship_type: 'relation',
  property: 'attribute',
} as const satisfies Record<ConceptKind, string>

/** A kind of Concept in the Map's and the Table's words: class, relation or attribute. */
export type ConceptNoun = (typeof CONCEPT_NOUN)[ConceptKind]

/**
 * A class or a relation, by name: a row of the Table, a search result, what "Show on Map"
 * shows.
 */
export interface ClassOrRelation {
  kind: (typeof CONCEPT_NOUN)[OwnerKind]
  label: string
}

/** An attribute's Concept, `<owner>.<attribute>` as the Diff names it, split into the two. */
export function attributeReference(concept: string): { owner: string; attribute: string } {
  const dot = concept.indexOf('.')
  return { owner: concept.slice(0, dot), attribute: concept.slice(dot + 1) }
}

/** A class Concept, placed in the hierarchy: `depth` 0 has no (known) superclass. */
export interface ClassRow {
  label: string
  description?: string
  deprecated: boolean
  parent?: string
  depth: number
  /** e.g. `UNIQUENESS (name)` */
  constraints: string[]
  /** How many attributes it declares itself. */
  attributes: number
  /** How many more it inherits along its superclass chain (a redeclared one counts as its own). */
  inheritedAttributes: number
  /** Its own Patterns out of it, each with its target, by relation then target. */
  outgoing: Connection[]
  /** Its own Patterns into it, each with its source, by relation then source. */
  incoming: Connection[]
}

/** One of a class's Patterns, seen from the class: its relation, and the class at its other end. */
export interface Connection {
  relation: string
  other: string
}

export interface RelationRow {
  label: string
  description?: string
  deprecated: boolean
  /** Its Patterns, in the order of their ids (`patternId`). */
  patterns: Pattern[]
  /** How many attributes it declares. */
  attributes: number
}

/** The Table's classes and relations; its attributes are `attributeRows`. */
export interface ConceptTables {
  classes: ClassRow[]
  relations: RelationRow[]
}

/** A Pattern: which class (source) may link to which (target) through a relation. */
export type Pattern = Ontology['patterns'][number]

/** A Pattern as `(Source)-[REL]->(Target)`, the syntax of `Pattern.__str__`. */
export const patternId = ([source, relation, target]: Pattern) =>
  `(${source})-[${relation}]->(${target})`

/** The constraints declared on class `label`, or only those on its attribute `name`. */
export const constraintsOn = (ontology: Ontology, label: string, name?: string) =>
  (ontology.constraints ?? []).filter(
    (c) => c.node_type === label && (name === undefined || c.property_name === name),
  )

/** The constraints declared on class `label`, each as e.g. `UNIQUENESS (name)`. */
export const constraintsOf = (ontology: Ontology, label: string) =>
  constraintsOn(ontology, label).map((c) => `${c.type} (${c.property_name})`)

/**
 * Class `label` and its ancestors, nearest first: the chain its attributes are inherited
 * along. It stops at a superclass the Ontology does not declare and never revisits a
 * class; empty when the Ontology has no class `label`.
 */
export function superclassChain(ontology: Ontology, label: string): OntologyConcept[] {
  const classes = new Map(ontology.node_types.map((n) => [n.label, n]))
  const chain: OntologyConcept[] = []
  let c = classes.get(label)
  while (c && !chain.includes(c)) {
    chain.push(c)
    c = c.parent === undefined ? undefined : classes.get(c.parent)
  }
  return chain
}

const byConnection = (a: Connection, b: Connection) =>
  codePointOrder(a.relation, b.relation) || codePointOrder(a.other, b.other)

/** An Ontology's classes, in hierarchy order, and relations, as the Table lists them. */
export function conceptTables(ontology: Ontology): ConceptTables {
  const labels = new Set(ontology.node_types.map((n) => n.label))
  const children = new Map<string | undefined, typeof ontology.node_types>()
  for (const node of ontology.node_types) {
    const parent = node.parent !== undefined && labels.has(node.parent) ? node.parent : undefined
    children.set(parent, [...(children.get(parent) ?? []), node])
  }

  // The attribute names a class inherits: its ancestors' that it does not redeclare.
  const inheritedNames = (node: OntologyConcept) => {
    const own = new Set((node.properties ?? []).map((p) => p.name))
    const inherited = superclassChain(ontology, node.label)
      .slice(1)
      .flatMap((c) => (c.properties ?? []).map((p) => p.name))
    return new Set(inherited.filter((name) => !own.has(name)))
  }

  const classes: ClassRow[] = []
  const visit = (parent: string | undefined, depth: number) => {
    const level = [...(children.get(parent) ?? [])].sort((a, b) => a.label.localeCompare(b.label))
    for (const node of level) {
      classes.push({
        label: node.label,
        description: node.description,
        deprecated: node.deprecated ?? false,
        parent: node.parent,
        depth,
        constraints: constraintsOf(ontology, node.label),
        attributes: (node.properties ?? []).length,
        inheritedAttributes: inheritedNames(node).size,
        outgoing: ontology.patterns
          .filter(([source]) => source === node.label)
          .map(([, relation, target]) => ({ relation, other: target }))
          .sort(byConnection),
        incoming: ontology.patterns
          .filter(([, , target]) => target === node.label)
          .map(([source, relation]) => ({ relation, other: source }))
          .sort(byConnection),
      })
      visit(node.label, depth + 1)
    }
  }
  visit(undefined, 0)

  const relations = ontology.relationship_types.map((rel): RelationRow => ({
    label: rel.label,
    description: rel.description,
    deprecated: rel.deprecated ?? false,
    patterns: ontology.patterns
      .filter(([, relationship]) => relationship === rel.label)
      .sort((a, b) => codePointOrder(patternId(a), patternId(b))),
    attributes: (rel.properties ?? []).length,
  }))

  return { classes, relations }
}
