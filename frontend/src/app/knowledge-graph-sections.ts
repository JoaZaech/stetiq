import { CircleArrowUp, Hammer, Layers, ListChecks, ScanEye, type LucideIcon } from 'lucide-react'

/**
 * The sections of a Knowledge Graph, in sidebar order. The sidebar renders one entry
 * per section, and `router.tsx` mounts each one at `/kg/:name/<path>` from its entry in
 * `knowledgeGraphSectionRoutes`. To build a section, replace its placeholder page there.
 */
export const KNOWLEDGE_GRAPH_SECTIONS = [
  { path: 'versions', label: 'Ontology Versions', icon: Layers },
  { path: 'runs', label: 'Construction Runs', icon: Hammer },
  { path: 'use-case', label: 'Use Case', icon: ListChecks },
  { path: 'observations', label: 'Observations', icon: ScanEye },
  { path: 'promotions', label: 'Promotions', icon: CircleArrowUp },
] as const satisfies readonly { path: string; label: string; icon: LucideIcon }[]

export type KnowledgeGraphSection = (typeof KNOWLEDGE_GRAPH_SECTIONS)[number]
export type KnowledgeGraphSectionPath = KnowledgeGraphSection['path']

export function knowledgeGraphSection(path: KnowledgeGraphSectionPath): KnowledgeGraphSection {
  return KNOWLEDGE_GRAPH_SECTIONS.find((s) => s.path === path)!
}

/** The section a Knowledge Graph opens on. */
export const DEFAULT_SECTION: KnowledgeGraphSectionPath = 'versions'

/** App path (under `/ui`) of a Knowledge Graph page, e.g. `kgUrl('support', 'versions', 3)`. */
export function kgUrl(name: string, section?: KnowledgeGraphSectionPath, ...rest: (string | number)[]) {
  return ['/kg', name, ...(section ? [section] : []), ...rest]
    .map((part, i) => (i === 0 ? part : encodeURIComponent(String(part))))
    .join('/')
}

/** Sections with a compare page at `<section>/compare`. */
export type ComparableSection = Extract<KnowledgeGraphSectionPath, 'versions' | 'runs' | 'use-case'>

/** The search param naming the compared items on every compare page: repeated, oldest first. */
export const COMPARE_PARAM = 'id'

/**
 * App path of a section's compare page, e.g. `kgCompareUrl('support', 'versions', [2, 4])`
 * is `/kg/support/versions/compare?id=2&id=4`. Pass `ids` oldest first: a two-way
 * compare reads the first as what changed from.
 */
export function kgCompareUrl(name: string, section: ComparableSection, ids: readonly (string | number)[]) {
  const query = new URLSearchParams(ids.map((id) => [COMPARE_PARAM, String(id)]))
  return `${kgUrl(name, section, 'compare')}?${query}`
}
