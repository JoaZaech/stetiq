/** Paths between two classes on the Map, inherited Patterns included. */
import type { OntologyMap } from './ontology-map'

/** One step of a path: from one class to the next. */
export interface PathStep {
  /** Link ids of every Pattern link that joins the two classes, sorted: the step can take any of them. */
  links: string[]
  /**
   * The superclasses, sorted, that the step climbs from either of its classes to reach an
   * inherited Pattern's class; empty when every link is the classes' own.
   */
  ancestors: string[]
}

/** A path between two classes: the classes it passes, in order, and the steps between them. */
export interface MapPath {
  classes: string[]
  steps: PathStep[]
}

/**
 * Every shortest path from class `from` to class `to`, over Pattern links taken either way
 * round. A class also takes part in each Pattern of its superclasses, at that superclass's
 * end: inherited Patterns are derived here, along the Map's subclass links, and never become
 * links of their own. Empty when no path exists, or either class is not on the Map.
 */
export function shortestPaths(map: OntologyMap, from: string, to: string): MapPath[] {
  const labels = new Set(map.nodes.map((n) => n.label))
  if (!labels.has(from) || !labels.has(to)) return []
  const parents = new Map(map.subclassLinks.map((l) => [l.child, l.parent]))
  // A class, then its superclasses, nearest first; a cycle ends the chain.
  const chain = (c: string) => {
    const classes = [c]
    let parent = parents.get(c)
    while (parent !== undefined && !classes.includes(parent)) {
      classes.push(parent)
      parent = parents.get(parent)
    }
    return classes
  }
  const chains = new Map([...labels].map((c) => [c, chain(c)]))
  const stepBetween = (a: string, b: string): PathStep => {
    const [chainOfA, chainOfB] = [chains.get(a)!, chains.get(b)!]
    const links: string[] = []
    const ancestors = new Set<string>()
    for (const l of map.links) {
      // Either way round: one class's chain holds the link's source, the other's its target.
      for (const [sourceChain, targetChain] of [[chainOfA, chainOfB], [chainOfB, chainOfA]]) {
        // How many superclasses up each chain the link's end sits; -1 when it is not there.
        const [sourceHeight, targetHeight] = [sourceChain.indexOf(l.source), targetChain.indexOf(l.target)]
        if (sourceHeight === -1 || targetHeight === -1) continue
        if (!links.includes(l.id)) links.push(l.id)
        const climbed = [...sourceChain.slice(1, sourceHeight + 1), ...targetChain.slice(1, targetHeight + 1)]
        for (const c of climbed) ancestors.add(c)
      }
    }
    return { links: links.sort(), ancestors: [...ancestors].sort() }
  }

  // Breadth first from `from`, keeping every previous class at the shortest distance.
  const previous = new Map<string, string[]>([[from, []]])
  let frontier = [from]
  while (frontier.length > 0 && !previous.has(to)) {
    const next = new Map<string, string[]>()
    for (const a of frontier) {
      for (const b of [...labels].sort()) {
        if (previous.has(b) || stepBetween(a, b).links.length === 0) continue
        next.set(b, [...(next.get(b) ?? []), a])
      }
    }
    for (const [b, before] of next) previous.set(b, before)
    frontier = [...next.keys()]
  }
  if (!previous.has(to)) return []

  // Every path back from `to`, then each reversed to run from `from`.
  const back = (c: string): string[][] =>
    c === from ? [[from]] : previous.get(c)!.flatMap((p) => back(p).map((path) => [...path, c]))
  return back(to).map((classes) => ({
    classes,
    steps: classes.slice(1).map((b, i) => stepBetween(classes[i], b)),
  }))
}
