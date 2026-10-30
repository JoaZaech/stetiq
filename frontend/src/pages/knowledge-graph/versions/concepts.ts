import type { Ontology, OntologyConcept } from '@/api/ontology-versions'

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
  /** Its own Patterns out of it, as `HAS_TRIP → Trip` (relation, then target), sorted. */
  outgoing: string[]
  /** Its own Patterns into it, as `HAS_TRIP ← Route` (relation, then source), sorted. */
  incoming: string[]
}

export interface RelationRow {
  label: string
  description?: string
  deprecated: boolean
  /** `(Source)-[REL]->(Target)`, the syntax of `Pattern.__str__`. */
  patterns: string[]
  /** How many attributes it declares. */
  attributes: number
}

export interface AttributeRow {
  /** The class or relation that declares it. */
  owner: string
  name: string
  type: string
  description?: string
  required: boolean
}

export interface ConceptTables {
  classes: ClassRow[]
  relations: RelationRow[]
  attributes: AttributeRow[]
}

/** A Pattern as `(Source)-[REL]->(Target)`, the syntax of `Pattern.__str__`. */
export const patternId = ([source, relation, target]: Ontology['patterns'][number]) =>
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

/** An Ontology's Concepts as three tables: classes in hierarchy order, relations, attributes. */
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
          .map(([, relation, target]) => `${relation} → ${target}`)
          .sort(),
        incoming: ontology.patterns
          .filter(([, , target]) => target === node.label)
          .map(([source, relation]) => `${relation} ← ${source}`)
          .sort(),
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
      .map(patternId)
      .sort(),
    attributes: (rel.properties ?? []).length,
  }))

  const attributes = [...ontology.node_types, ...ontology.relationship_types].flatMap((owner) =>
    (owner.properties ?? []).map((p) => ({
      owner: owner.label,
      name: p.name,
      type: p.type,
      description: p.description,
      required: p.required ?? false,
    })),
  )

  return { classes, relations, attributes }
}
