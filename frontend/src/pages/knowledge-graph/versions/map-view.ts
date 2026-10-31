/** An Ontology, or a comparison of two, drawn as a Map or listed as tables. */
export type MapView = 'map' | 'table'

/** Map first: the default, with `?view=` absent. */
export const MAP_VIEWS: readonly [MapView, ...MapView[]] = ['map', 'table']

/**
 * How tall the Map is: down to near the window's bottom from where it sits under the
 * page's header, tabs and toolbar (about 18rem), so the readable zoom rarely leaves a
 * small Ontology to pan; never less than 32rem. Its loading placeholder is as tall.
 */
export const MAP_HEIGHT = 'h-[max(32rem,calc(100dvh-18rem))]'
