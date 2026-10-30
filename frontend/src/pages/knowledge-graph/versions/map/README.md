# map/

The Ontology Map: an Ontology Version drawn as a node-link diagram, on the Ontology tab and (with a comparison) on the Changes tab and Compare page.

**Entry point:** `OntologyMap.tsx` (`OntologyMap`), the React Flow canvas. Its side panels are `MapDetailsPanel`, `MapPathPanel` and `MapSearchResults`, framed by `MapSidePanel`.

**Pure modules** (no React, each with a `.test.ts`):

- `ontology-map.ts`: the Ontology as a node-link dataset (`ontologyMap`) and its filters (`filterOntologyMap`).
- `ontology-map-layout.ts`: where each class goes, a seeded ELK stress layout (`layoutOntologyMap`).
- `ontology-map-sizes.ts`: node and label sizes from monospace text length (`classSizes`, `labelSize`).
- `ontology-map-links.ts`: a Pattern link's shape and when its label shows (`linkShape`, `labelShown`).
- `ontology-map-focus.ts`: a selection's focus and details (`focusOf`, `detailsOf`, `MapSelection`).
- `ontology-map-paths.ts`: shortest paths between two classes (`shortestPaths`).
- `ontology-map-search.ts`: the Concept search (`searchOntology`).
- `ontology-map-centre.ts`: where the Map centres (`centreOf`, `locatedSelection`).

`ontology-map.fixtures.ts` holds the Ontologies the Map's tests share. Superimposing two versions lives in `../comparison/`; the selection, Concepts and Table/Map toggle stay in `..`.
