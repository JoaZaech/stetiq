import { Outlet } from 'react-router'
import { isNotFound } from '@/api/client'
import { useKnowledgeGraph } from '@/api/knowledge-graph'
import { ErrorAlert } from '@/components/ErrorAlert'
import { Skeleton } from '@/components/ui/skeleton'
import { NotFoundPage } from '@/pages/NotFoundPage'
import { useKnowledgeGraphName } from './params'

/**
 * The route element of `/kg/:name`: every Knowledge Graph page renders inside it, and
 * only once the Knowledge Graph is known to exist and be readable. Unknown and
 * unreadable ones both show the same not-found page.
 */
export function KnowledgeGraphLayout() {
  const name = useKnowledgeGraphName()
  const kg = useKnowledgeGraph(name)
  if (kg.isPending) return <Skeleton className="h-24 w-full" />
  if (kg.isError) {
    return isNotFound(kg.error) ? (
      <NotFoundPage
        title="Knowledge Graph not found"
        message={`There is no Knowledge Graph called “${name}” that you can read.`}
      />
    ) : (
      <ErrorAlert error={kg.error} />
    )
  }
  return <Outlet />
}
