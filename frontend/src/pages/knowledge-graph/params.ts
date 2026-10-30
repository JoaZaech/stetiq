import { useParams } from 'react-router'

/** The `:name` of the Knowledge Graph route every page under `/kg/:name` sits in. */
export function useKnowledgeGraphName(): string {
  const { name } = useParams()
  if (name === undefined) throw new Error('useKnowledgeGraphName outside a /kg/:name route')
  return name
}
