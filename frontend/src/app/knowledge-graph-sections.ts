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

/** App path (under `/ui`) of the Knowledge Graph list; every Knowledge Graph page sits below it. */
export const kgListUrl = '/kg'

/** App path (under `/ui`) of a Knowledge Graph page, e.g. `kgUrl('support', 'versions', 3)`. */
export function kgUrl(name: string, section?: KnowledgeGraphSectionPath, ...rest: (string | number)[]) {
  return [kgListUrl, name, ...(section ? [section] : []), ...rest]
    .map((part, i) => (i === 0 ? part : encodeURIComponent(String(part))))
    .join('/')
}

/**
 * Where the Knowledge Graph switcher goes when the user picks `target` while on
 * `location` (an app path, query allowed): the same section of `target`, without any
 * detail or compare page below it (their ids belong to the other Knowledge Graph), or
 * `target`'s default section when no section is open.
 */
export function switchKnowledgeGraphUrl(location: string, target: string): string {
  const [, root, , section] = location.split('?')[0].split('/')
  if (`/${root}` !== kgListUrl) return kgUrl(target, DEFAULT_SECTION)
  const openSection = KNOWLEDGE_GRAPH_SECTIONS.find((s) => s.path === section)
  return kgUrl(target, openSection?.path ?? DEFAULT_SECTION)
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
