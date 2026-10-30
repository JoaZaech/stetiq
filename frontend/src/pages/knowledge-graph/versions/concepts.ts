import type { Ontology } from '@/api/ontology-versions'

/** A class Concept, placed in the hierarchy: `depth` 0 has no (known) superclass. */
export interface ClassRow {
  label: string
  description?: string
  deprecated: boolean
  parent?: string
  depth: number
  /** e.g. `UNIQUENESS (name)` */
  constraints: string[]
}

export interface RelationRow {
  label: string
  description?: string
  deprecated: boolean
  /** `(Source)-[REL]->(Target)`, the syntax of `Pattern.__str__`. */
  patterns: string[]
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

/** An Ontology's Concepts as three tables: classes in hierarchy order, relations, attributes. */
export function conceptTables(ontology: Ontology): ConceptTables {
  const labels = new Set(ontology.node_types.map((n) => n.label))
  const children = new Map<string | undefined, typeof ontology.node_types>()
  for (const node of ontology.node_types) {
    const parent = node.parent !== undefined && labels.has(node.parent) ? node.parent : undefined
    children.set(parent, [...(children.get(parent) ?? []), node])
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
        constraints: (ontology.constraints ?? [])
          .filter((c) => c.node_type === node.label)
          .map((c) => `${c.type} (${c.property_name})`),
      })
      visit(node.label, depth + 1)
    }
  }
  visit(undefined, 0)

  const relations = ontology.relationship_types.map((rel) => ({
    label: rel.label,
    description: rel.description,
    deprecated: rel.deprecated ?? false,
    patterns: ontology.patterns
      .filter(([, relationship]) => relationship === rel.label)
      .map(([source, relationship, target]) => `(${source})-[${relationship}]->(${target})`)
      .sort(),
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

/** The Concepts whose name or description (or, for attributes, owner) contains `query`. */
export function searchConcepts(tables: ConceptTables, query: string): ConceptTables {
  const q = query.trim().toLowerCase()
  if (q === '') return tables
  const matches = (...texts: (string | undefined)[]) =>
    texts.some((t) => t !== undefined && t.toLowerCase().includes(q))
  return {
    classes: tables.classes.filter((c) => matches(c.label, c.description)),
    relations: tables.relations.filter((r) => matches(r.label, r.description)),
    attributes: tables.attributes.filter((a) => matches(a.owner, a.name, a.description)),
  }
}
