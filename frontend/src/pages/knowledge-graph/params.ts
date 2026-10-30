import { useParams, useSearchParams } from 'react-router'
import { COMPARE_PARAM } from '@/app/knowledge-graph-sections'

/** The ids a compare page shows, oldest first (`?id=…&id=…`, see `kgCompareUrl`). */
export function useComparedIds(): string[] {
  const [params] = useSearchParams()
  return params.getAll(COMPARE_PARAM)
}

/** The `:name` of the Knowledge Graph route every page under `/kg/:name` sits in. */
export function useKnowledgeGraphName(): string {
  const { name } = useParams()
  if (name === undefined) throw new Error('useKnowledgeGraphName outside a /kg/:name route')
  return name
}
