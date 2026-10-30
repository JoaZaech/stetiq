import { useId, useMemo } from 'react'
import { Link } from 'react-router'
import { type KnowledgeGraphSummary, useKnowledgeGraphs } from '@/api/knowledge-graphs'
import { DataTable } from '@/components/DataTable'
import { ErrorAlert } from '@/components/ErrorAlert'
import { Skeleton } from '@/components/ui/skeleton'
import { useDataTable } from '@/lib/data-table'
import { knowledgeGraphColumns } from '@/pages/knowledge-graphs/knowledge-graph-columns'
import { NoKnowledgeGraphs } from '@/pages/knowledge-graphs/NoKnowledgeGraphs'

const RECENT_COUNT = 5

/** The `count` most recently modified Knowledge Graphs, newest first; never-modified ones last. */
function mostRecent(knowledgeGraphs: readonly KnowledgeGraphSummary[], count: number) {
  const at = (kg: KnowledgeGraphSummary) => (kg.last_modified_at ? Date.parse(kg.last_modified_at) : -Infinity)
  return [...knowledgeGraphs].sort((a, b) => at(b) - at(a)).slice(0, count)
}

/** Home's Recent Knowledge Graphs block, from the same list the `/kg` page shows. */
export function RecentKnowledgeGraphs() {
  const knowledgeGraphs = useKnowledgeGraphs()
  const headingId = useId()

  return (
    <section aria-labelledby={headingId} className="space-y-3">
      <div className="flex items-baseline justify-between gap-4">
        <h2 id={headingId} className="text-base font-semibold">
          Recent Knowledge Graphs
        </h2>
        <Link to="/kg" className="text-sm text-primary underline-offset-4 hover:underline">
          View all
        </Link>
      </div>
      {knowledgeGraphs.isPending ? (
        <Skeleton className="h-40 w-full" />
      ) : knowledgeGraphs.isError ? (
        <ErrorAlert error={knowledgeGraphs.error} title="Could not load the Knowledge Graphs" />
      ) : knowledgeGraphs.data.length === 0 ? (
        <NoKnowledgeGraphs headingLevel={3} />
      ) : (
        <RecentTable data={knowledgeGraphs.data} />
      )}
    </section>
  )
}

function RecentTable({ data }: { data: KnowledgeGraphSummary[] }) {
  const recent = useMemo(() => mostRecent(data, RECENT_COUNT), [data])
  const table = useDataTable({ data: recent, columns: knowledgeGraphColumns })
  return <DataTable table={table} empty="No Knowledge Graphs yet" />
}
