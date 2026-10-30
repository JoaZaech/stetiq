/**
 * The Map's Concept search: it locates a class or relation by name, and lists the other
 * Concepts a search mentions, each with its reason.
 */
import type { Ontology, OntologyConcept } from '@/api/ontology-versions'

/** A class or relation the search found. */
export interface SearchResult {
  kind: 'class' | 'relation'
  label: string
}

/** A Concept found by something other than its name, e.g. "description mentions 'warehouse'". */
export interface OtherSearchResult extends SearchResult {
  reasons: string[]
}

export interface SearchResults {
  /** Concepts whose name contains the search: the exact name first, then names that start with it. */
  names: SearchResult[]
  /** Every other Concept whose description or attributes mention it, classes first. */
  others: OtherSearchResult[]
}

/** How well a name matches: an exact name first, then a prefix, then anywhere in it. */
const nameRank = (name: string, q: string) => (name === q ? 0 : name.startsWith(q) ? 1 : 2)

/**
 * What the search `query` finds, ignoring case: the classes and relations it names, and
 * the others whose description or one of whose attributes (by name or description)
 * mentions it. An empty search finds nothing.
 */
export function searchOntology(ontology: Ontology, query: string): SearchResults {
  const q = query.trim().toLowerCase()
  if (q === '') return { names: [], others: [] }
  /** `text` as written where it contains the search, or undefined. */
  const mention = (text?: string) => {
    const at = text?.toLowerCase().indexOf(q) ?? -1
    return at < 0 ? undefined : text!.slice(at, at + q.length)
  }
  const reasonsOf = (concept: OntologyConcept) => {
    const reasons: string[] = []
    const described = mention(concept.description)
    if (described !== undefined) reasons.push(`description mentions '${described}'`)
    for (const p of concept.properties ?? []) {
      if (mention(p.name) !== undefined) reasons.push(`attribute \`${p.name}\``)
      else {
        const attributeDescribed = mention(p.description)
        if (attributeDescribed !== undefined)
          reasons.push(`attribute \`${p.name}\`: description mentions '${attributeDescribed}'`)
      }
    }
    return reasons
  }

  const concepts = [
    ...ontology.node_types.map((c) => ({ kind: 'class' as const, concept: c })),
    ...ontology.relationship_types.map((c) => ({ kind: 'relation' as const, concept: c })),
  ]
  const names: (SearchResult & { rank: number })[] = []
  const others: OtherSearchResult[] = []
  for (const { kind, concept } of concepts) {
    const name = concept.label.toLowerCase()
    if (name.includes(q)) {
      names.push({ kind, label: concept.label, rank: nameRank(name, q) })
      continue
    }
    const reasons = reasonsOf(concept)
    if (reasons.length > 0) others.push({ kind, label: concept.label, reasons })
  }
  // Concepts arrive classes first, each kind sorted by label, and the sort is stable.
  return {
    names: names.sort((a, b) => a.rank - b.rank).map(({ kind, label }) => ({ kind, label })),
    others,
  }
}
