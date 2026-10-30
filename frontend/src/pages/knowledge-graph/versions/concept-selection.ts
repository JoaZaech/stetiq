/**
 * The selected Concept, shared by the Ontology Table and the Map and kept in the URL
 * (`?select=`), so it survives a reload, can be shared, and carries over when switching
 * views. One value, a kind and a name:
 *
 * - `class:Trip`: a class;
 * - `relation:HAS_TRIP`: a relation, which the Map shows as one of its Pattern links;
 * - `link:(Route)-[HAS_TRIP]->(Trip)`: one Pattern link, by its id;
 * - `path:Customer->Product`: two classes, for the shortest paths between them.
 */
import { useCallback, useMemo } from 'react'
import { useSearchParams } from 'react-router'
import type { Ontology } from '@/api/ontology-versions'
import { setOrDeleteParam } from '@/lib/search-params'
import { type ClassOrRelation, patternId } from './concepts'
import type { MapSelection } from './ontology-map-focus'

/** What is selected: anything the Map selects, or a relation as a whole (from the Table). */
export type ConceptSelection = MapSelection | { kind: 'relation'; label: string }

export const SELECT_PARAM = 'select'

const PATH_SEPARATOR = '->'

/** The selection `value` (a `?select=` param) names; null when absent or not one. */
export function parseSelection(value: string | null): ConceptSelection | null {
  if (!value) return null
  const colon = value.indexOf(':')
  if (colon < 0) return null
  const kind = value.slice(0, colon)
  const name = value.slice(colon + 1)
  if (name === '') return null
  if (kind === 'class' || kind === 'relation') return { kind, label: name }
  if (kind === 'link') return { kind, id: name }
  if (kind === 'path') {
    const at = name.lastIndexOf(PATH_SEPARATOR)
    const [from, to] = [name.slice(0, at), name.slice(at + PATH_SEPARATOR.length)]
    return at > 0 && to !== '' ? { kind, from, to } : null
  }
  return null
}

/** `selection` as a `?select=` value. */
export function formatSelection(selection: ConceptSelection): string {
  switch (selection.kind) {
    case 'class':
    case 'relation':
      return `${selection.kind}:${selection.label}`
    case 'link':
      return `link:${selection.id}`
    case 'path':
      return `path:${selection.from}${PATH_SEPARATOR}${selection.to}`
  }
}

/** The classes and relations whose Table rows are highlighted, by label. */
export interface SelectedRows {
  classes: ReadonlySet<string>
  relations: ReadonlySet<string>
}

/**
 * The Table rows a selection highlights: the class or relation selected, a link's
 * relation, or both classes of a path.
 */
export function selectedRows(ontology: Ontology, selection: ConceptSelection | null): SelectedRows {
  const classes = new Set<string>()
  const relations = new Set<string>()
  if (selection?.kind === 'class') classes.add(selection.label)
  else if (selection?.kind === 'relation') relations.add(selection.label)
  else if (selection?.kind === 'path') [selection.from, selection.to].forEach((c) => classes.add(c))
  else if (selection?.kind === 'link') {
    const pattern = ontology.patterns.find((p) => patternId(p) === selection.id)
    if (pattern) relations.add(pattern[1])
  }
  return { classes, relations }
}

/** Whether `concept`'s rows are among the highlighted `rows`. */
export const isSelectedRow = (rows: SelectedRows, { kind, label }: ClassOrRelation) =>
  (kind === 'class' ? rows.classes : rows.relations).has(label)

const write = (p: URLSearchParams, selection: ConceptSelection | null) =>
  setOrDeleteParam(p, SELECT_PARAM, selection && formatSelection(selection))

/**
 * The selection in `?select=` and a setter for it. Selecting replaces the history entry,
 * as a grid's sort does, and keeps the other params.
 */
export function useConceptSelection(): [
  ConceptSelection | null,
  (selection: ConceptSelection | null) => void,
] {
  const [params, setParams] = useSearchParams()
  const value = params.get(SELECT_PARAM)
  const selection = useMemo(() => parseSelection(value), [value])
  const setSelection = useCallback(
    (next: ConceptSelection | null) => setParams((p) => write(p, next), { replace: true }),
    [setParams],
  )
  return [selection, setSelection]
}

/**
 * "Show on Map": switches the page to its Map (`?view=` absent) with `selection` selected,
 * which the Map centres on when it opens. Adds a history entry, as the view toggle does.
 */
export function useShowOnMap(): (selection: ConceptSelection) => void {
  const [, setParams] = useSearchParams()
  return useCallback(
    (selection: ConceptSelection) =>
      setParams((p) => {
        p.delete('view')
        return write(p, selection)
      }),
    [setParams],
  )
}
