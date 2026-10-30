import { useId, useMemo } from 'react'
import { Link } from 'react-router'
import { kgListUrl } from '@/app/knowledge-graph-sections'
import type { KnowledgeGraphSummary } from '@/api/knowledge-graphs'
import { DataTable } from '@/components/DataTable'
import { Skeleton } from '@/components/ui/skeleton'
import { useDataTable } from '@/lib/data-table'
import { knowledgeGraphColumns } from '@/pages/knowledge-graphs/knowledge-graph-columns'
import { KnowledgeGraphsLoaded } from '@/pages/knowledge-graphs/KnowledgeGraphsLoaded'

const RECENT_COUNT = 5

/** The `count` most recently modified Knowledge Graphs, newest first; never-modified ones last. */
function mostRecent(knowledgeGraphs: readonly KnowledgeGraphSummary[], count: number) {
  const at = (kg: KnowledgeGraphSummary) => (kg.last_modified_at ? Date.parse(kg.last_modified_at) : -Infinity)
  return [...knowledgeGraphs].sort((a, b) => at(b) - at(a)).slice(0, count)
}

/** Home's Recent Knowledge Graphs block, from the same list the `/kg` page shows. */
export function RecentKnowledgeGraphs() {
  const headingId = useId()

  return (
    <section aria-labelledby={headingId} className="space-y-3">
      <div className="flex items-baseline justify-between gap-4">
        <h2 id={headingId} className="text-base font-semibold">
          Recent Knowledge Graphs
        </h2>
        <Link to={kgListUrl} className="text-sm text-primary underline-offset-4 hover:underline">
          View all
        </Link>
      </div>
      <KnowledgeGraphsLoaded pending={<Skeleton className="h-40 w-full" />} headingLevel={3}>
        {(data) => <RecentTable data={data} />}
      </KnowledgeGraphsLoaded>
    </section>
  )
}

function RecentTable({ data }: { data: KnowledgeGraphSummary[] }) {
  const recent = useMemo(() => mostRecent(data, RECENT_COUNT), [data])
  const table = useDataTable({ data: recent, columns: knowledgeGraphColumns })
  return <DataTable table={table} empty="No Knowledge Graphs yet" />
}
