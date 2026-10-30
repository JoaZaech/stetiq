import { Search } from 'lucide-react'
import { useSearchParams } from 'react-router'
import { type KnowledgeGraphSummary, useKnowledgeGraphs } from '@/api/knowledge-graphs'
import { DataTable } from '@/components/DataTable'
import { ErrorAlert } from '@/components/ErrorAlert'
import { PageHeader } from '@/components/PageHeader'
import { Input } from '@/components/ui/input'
import { Skeleton } from '@/components/ui/skeleton'
import { useDataTable } from '@/lib/data-table'
import { knowledgeGraphColumns } from './knowledge-graph-columns'
import { NoKnowledgeGraphs } from './NoKnowledgeGraphs'

/** `/kg`: every Knowledge Graph the user can read, with its state at a glance. */
export function KnowledgeGraphsPage() {
  const knowledgeGraphs = useKnowledgeGraphs()
  return (
    <>
      <PageHeader
        title="Knowledge Graphs"
        description="The Knowledge Graphs you can read, with their Ontology Versions and Construction Runs."
      />
      {knowledgeGraphs.isPending ? (
        <div className="space-y-2">
          <Skeleton className="h-9 w-72" />
          <Skeleton className="h-40 w-full" />
        </div>
      ) : knowledgeGraphs.isError ? (
        <ErrorAlert error={knowledgeGraphs.error} title="Could not load the Knowledge Graphs" />
      ) : knowledgeGraphs.data.length === 0 ? (
        <NoKnowledgeGraphs />
      ) : (
        <KnowledgeGraphTable data={knowledgeGraphs.data} />
      )}
    </>
  )
}

function KnowledgeGraphTable({ data }: { data: KnowledgeGraphSummary[] }) {
  // The search lives in the URL (?q=), so a filtered list can be shared.
  const [searchParams, setSearchParams] = useSearchParams()
  const search = searchParams.get('q') ?? ''
  const table = useDataTable({
    data,
    columns: knowledgeGraphColumns,
    state: { columnFilters: search ? [{ id: 'name', value: search }] : [] },
  })

  const setSearch = (value: string) =>
    setSearchParams(
      (params) => {
        if (value) params.set('q', value)
        else params.delete('q')
        return params
      },
      { replace: true },
    )

  return (
    <div className="space-y-3">
      <div className="relative w-72 max-w-full">
        <Search aria-hidden className="absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-muted-foreground" />
        <Input
          type="search"
          aria-label="Search Knowledge Graphs"
          placeholder="Search by name"
          className="pl-8"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
      </div>
      <DataTable table={table} empty={`No Knowledge Graph matches “${search}”`} />
    </div>
  )
}
