/**
 * What the Map draws, and how it answers the user: the Map's view state. It takes the
 * Ontology (or a comparison), the page's `?select=`, the Concept search, the Map's filters
 * and the user's gestures, and returns the selection, its focus, details and paths, the
 * search results, how each item is emphasized or faded, and whether to centre.
 * `OntologyMap` renders the `DrawnMap` that `createDrawnMapOf`'s function computes and forwards gestures to
 * `respondTo`.
 */
import type { Ontology } from '@/api/ontology-versions'
import type { OntologyChange } from '@/api/ontology-diff'
import { changesOf, type OntologyComparison, selectionOf } from '../comparison/ontology-map-comparison'
import { type ConceptSelection, formatSelection, parseSelection } from '../concept-selection'
import type { ClassOrRelation } from '../concepts'
import { firstFramed, locatedSelection } from './ontology-map-centre'
import { filterOntologyMap, ontologyMap, type MapFilters, type OntologyMap } from './ontology-map'
import {
  changedOf,
  contextOf,
  detailsOf,
  focusOf,
  pathFocus,
  pathsBetween,
  relationSelection,
  searchMap,
  type MapDetails,
  type MapFocus,
  type MapSelection,
} from './ontology-map-focus'
import type { MapPath } from './ontology-map-paths'
import { type SearchResults, searchOntology } from './ontology-map-search'

// Emphasis types are aliases, not interfaces: React Flow's node and edge data must be indexable.

/**
 * How an item is drawn against the selection and the search: `selected` is the selection
 * itself, `match` a search match, `context` out of the selection's focus but changed in a
 * comparison, so it stays readable, and `faded` is out of the focus and unchanged or, with
 * no selection, not a match of an active search.
 */
export type Emphasis = {
  selected: boolean
  match: boolean
  context: boolean
  faded: boolean
}

/** A Pattern link's emphasis; `focused`: in the focus, so its label shows at any zoom. */
export type LinkEmphasis = Emphasis & { focused: boolean }

/** What the Map is given: an Ontology, or a comparison of two, and the page's selection and search. */
export type MapInput = {
  /** The page's selection, its `?select=`. */
  selected: ConceptSelection | null
  /** The Concept search. */
  query: string
} & ({ ontology: Ontology; comparison?: never } | { comparison: OntologyComparison; ontology?: never })

/** What the Map keeps of its own between gestures. */
export interface MapState {
  filters: MapFilters
  /** What the change summary points at: its focus shows, without selecting it. */
  preview: MapSelection | null
  /**
   * The selection the Map opened on or a search result picked (as a `?select=` value),
   * which the Map stays centred on while it lasts.
   */
  located: string | null
}

/** The state of a Map opened on `selected`: unfiltered, and centred on `selected`. */
export const initialMapState = (selected: ConceptSelection | null): MapState => ({
  filters: { hideDeprecated: false, hideSubclassLinks: false },
  preview: null,
  located: selected && formatSelection(selected),
})

/** What the Map draws. */
export interface DrawnMap {
  input: MapInput
  state: MapState
  /** The whole Map, as it is laid out; filters only hide. */
  map: OntologyMap
  /** What the filters leave shown. */
  shown: OntologyMap
  /** The page's selection on the Map: null when nothing, or nothing shown, is selected. */
  selection: MapSelection | null
  /** What stays in focus (the preview's, else the selection's); null when nothing fades for it. */
  focus: MapFocus | null
  /** The selection's details, when it is in focus. */
  details: MapDetails | null
  /** The shortest paths, for a path selection whose two classes are shown. */
  paths: MapPath[] | null
  /** The Concept search's results. */
  results: SearchResults
  /** Each shown class's emphasis, by label. */
  classes: Record<string, Emphasis>
  /** Each shown Pattern link's emphasis, by id. */
  links: Record<string, LinkEmphasis>
  /** Whether each shown subclass link is faded, by id. */
  subclassLinks: Record<string, { faded: boolean }>
  /** In a comparison, the Ontology Diff's changes behind the selection; null outside one. */
  changes: OntologyChange[] | null
  /** What to centre on (`centreOf`): the selection, while it is still the one located. */
  centreOn: MapSelection | null
  /** Whether to fit the Map in view: it opened on no selection. */
  fitView: boolean
  /** The classes that fit frames (`firstFramed`): a comparison's changes; null for the whole Map. */
  fitTo: string[] | null
}

/** `f`, remembering its last result while its arguments stay the same. */
function remember<A extends unknown[], R>(f: (...args: A) => R): (...args: A) => R {
  let last: { args: A; result: R } | undefined
  return (...args) => {
    if (!last || args.some((a, i) => !Object.is(a, last!.args[i]))) last = { args, result: f(...args) }
    return last.result
  }
}

/**
 * A function from what one Map is given and its state to what it draws, for that Map
 * alone (each `OntologyMap` makes its own). Each step is remembered, so it only runs again when its own inputs change: the shortest
 * paths when the selection or what is reachable changes, the search when the query does.
 */
export function createDrawnMapOf(): (input: MapInput, state: MapState) => DrawnMap {
  const mapOf = remember((ontology: Ontology) => ontologyMap(ontology))
  const shownOf = remember(filterOntologyMap)
  // Focus is over what is shown, so a selection a filter hides is no selection. Hiding
  // subclass links only declutters: a path through an inherited Pattern still counts.
  const reachableOf = remember((map: OntologyMap, filters: MapFilters, shown: OntologyMap) =>
    filters.hideSubclassLinks ? filterOntologyMap(map, { ...filters, hideSubclassLinks: false }) : shown,
  )
  // By its `?select=` value, which outlasts the object read from it.
  const selectionFor = remember((value: string | null, shown: OntologyMap, comparison: OntologyComparison | undefined) =>
    mapSelectionOf(parseSelection(value), shown, comparison),
  )
  const pathsOf = remember((reachable: OntologyMap, selection: MapSelection | null) =>
    selection?.kind === 'path' ? pathsBetween(reachable, selection) : null,
  )
  const selectedFocusOf = remember(
    (reachable: OntologyMap, selection: MapSelection | null, paths: MapPath[] | null) =>
      selection?.kind === 'path' ? paths && pathFocus(selection, paths) : focusOf(reachable, selection),
  )
  const focusOfPreview = remember(
    (reachable: OntologyMap, preview: MapSelection | null, selectedFocus: MapFocus | null) =>
      preview ? focusOf(reachable, preview) : selectedFocus,
  )
  const resultsOf = remember(searchOntology)
  const matchesOf = remember(searchMap)
  const detailsOfSelection = remember(
    (ontology: Ontology, selection: MapSelection | null, selectedFocus: MapFocus | null) =>
      selectedFocus ? detailsOf(ontology, selection) : null,
  )
  const changesBehind = remember((comparison: OntologyComparison | undefined, selection: MapSelection | null) =>
    comparison ? changesOf(comparison, selection) : null,
  )
  const changedIn = remember((comparison: OntologyComparison | undefined) => comparison && changedOf(comparison))
  const fitToOf = remember((map: OntologyMap, changed: MapFocus | undefined) => changed ? firstFramed(map, changed) : null)
  const emphasisOf = remember(
    (
      shown: OntologyMap,
      selection: MapSelection | null,
      focus: MapFocus | null,
      matches: MapFocus | null,
      changed: MapFocus | undefined,
    ) => emphasize(shown, selection, focus, matches, changed),
  )

  return (input, state) => {
    const { comparison, selected, query } = input
    const ontology = comparison?.ontology ?? input.ontology!
    const map = comparison?.map ?? mapOf(ontology)
    const shown = shownOf(map, state.filters)
    const reachable = reachableOf(map, state.filters, shown)
    const selection = selectionFor(selected && formatSelection(selected), shown, comparison)
    const paths = pathsOf(reachable, selection)
    const selectedFocus = selectedFocusOf(reachable, selection, paths)
    const focus = focusOfPreview(reachable, state.preview, selectedFocus)
    const results = resultsOf(ontology, query)
    const matches = matchesOf(map, query, results)
    const changed = changedIn(comparison)
    return {
      input,
      state,
      map,
      shown,
      selection,
      focus,
      details: detailsOfSelection(ontology, selection, selectedFocus),
      paths,
      results,
      ...emphasisOf(shown, selection, focus, matches, changed),
      changes: changesBehind(comparison, selection),
      centreOn: locatedSelection(state.located, selected, selection),
      fitView: state.located === null,
      fitTo: fitToOf(map, changed),
    }
  }
}

/**
 * What selecting `concept` selects on the Map, given what is `shown`: a class, path or
 * link itself, and a relation one of its shown links, in a comparison the one the change
 * summary selects (`selectionOf`); null when none is shown.
 */
function mapSelectionOf(
  concept: ConceptSelection | null,
  shown: OntologyMap,
  comparison: OntologyComparison | undefined,
): MapSelection | null {
  if (concept?.kind !== 'relation') return concept
  return comparison
    ? selectionOf(comparison, concept, shown.links)
    : relationSelection(shown.links, concept.label, () => false)
}

/** What picking the search result `result` selects; null when it is not shown. */
function pickOf({ shown, input }: DrawnMap, { kind, label }: ClassOrRelation): ConceptSelection | null {
  if (kind === 'relation') return mapSelectionOf({ kind, label }, shown, input.comparison) && { kind, label }
  return shown.nodes.some((n) => n.label === label) ? { kind, label } : null
}

/** Whether the search result `result` can be picked: it is shown. */
export const canPick = (view: DrawnMap, result: ClassOrRelation): boolean => pickOf(view, result) !== null

/** What the user does on the Map. */
export type MapGesture =
  /** A click on a class; shift-clicking a second class asks for the shortest paths to it. */
  | { kind: 'click-class'; label: string; shift: boolean }
  /** A click on a Pattern link. */
  | { kind: 'click-link'; id: string }
  /** A click on the Map's background, or a details or path panel closed. */
  | { kind: 'clear' }
  /** The Escape key. */
  | { kind: 'escape' }
  /** A search result picked from the list beside the Map. */
  | { kind: 'pick'; result: ClassOrRelation }
  /** A Concept selected from the change summary, or nothing. */
  | { kind: 'select'; concept: ConceptSelection | null }
  /** The change summary pointing at an item, or at nothing. */
  | { kind: 'preview'; selection: MapSelection | null }
  /** A filter switched. */
  | { kind: 'filter'; filters: Partial<MapFilters> }

/**
 * How the Map answers a gesture on `view`: its next state, and `select`, the page's next
 * selection, when the gesture changes it.
 */
export function respondTo(
  view: DrawnMap,
  gesture: MapGesture,
): { state: MapState; select?: ConceptSelection | null } {
  const { state, selection } = view
  switch (gesture.kind) {
    case 'click-class': {
      const { label, shift } = gesture
      return {
        state,
        select:
          shift && selection?.kind === 'class' && selection.label !== label
            ? { kind: 'path', from: selection.label, to: label }
            : { kind: 'class', label },
      }
    }
    case 'click-link':
      return { state, select: { kind: 'link', id: gesture.id } }
    case 'clear':
      return { state, select: null }
    case 'escape':
      return selection ? { state, select: null } : { state }
    case 'pick': {
      // The Map stays centred on what is picked while it stays selected.
      const picked = pickOf(view, gesture.result)
      return { state: { ...state, located: picked && formatSelection(picked) }, select: picked }
    }
    case 'select':
      return { state, select: gesture.concept }
    case 'preview':
      return { state: { ...state, preview: gesture.selection } }
    case 'filter':
      return { state: { ...state, filters: { ...state.filters, ...gesture.filters } } }
  }
}

/**
 * How each shown item is drawn: the selection (a class, a link, or a path's two classes
 * and its links) selected, search matches matched, what is out of the focus but `changed`
 * in a comparison kept as context (`contextOf`), and the rest of what is out of the focus
 * faded, or, with no focus, what an active search does not match. A subclass link fades
 * with either of its classes.
 */
function emphasize(
  shown: OntologyMap,
  selection: MapSelection | null,
  focus: MapFocus | null,
  matches: MapFocus | null,
  changed: MapFocus | undefined,
): Pick<DrawnMap, 'classes' | 'links' | 'subclassLinks'> {
  const context = focus && changed ? contextOf(focus, changed) : null
  const faded = (key: string, focused?: Set<string>, kept?: Set<string>, matched?: Set<string>) =>
    focused ? !focused.has(key) && !kept?.has(key) : matched ? !matched.has(key) : false
  const classes = Object.fromEntries(
    shown.nodes.map(({ label }): [string, Emphasis] => [
      label,
      {
        selected:
          selection?.kind === 'class'
            ? selection.label === label
            : selection?.kind === 'path' && (selection.from === label || selection.to === label),
        match: matches?.classes.has(label) ?? false,
        context: context?.classes.has(label) ?? false,
        faded: faded(label, focus?.classes, context?.classes, matches?.classes),
      },
    ]),
  )
  const links = Object.fromEntries(
    shown.links.map(({ id }): [string, LinkEmphasis] => [
      id,
      {
        selected:
          selection?.kind === 'link' ? selection.id === id : selection?.kind === 'path' && (focus?.links.has(id) ?? false),
        match: matches?.links.has(id) ?? false,
        context: context?.links.has(id) ?? false,
        faded: faded(id, focus?.links, context?.links, matches?.links),
        focused: focus?.links.has(id) ?? false,
      },
    ]),
  )
  const subclassLinks = Object.fromEntries(
    shown.subclassLinks.map(({ id, child, parent }) => [
      id,
      { faded: (classes[child]?.faded ?? false) || (classes[parent]?.faded ?? false) },
    ]),
  )
  return { classes, links, subclassLinks }
}
