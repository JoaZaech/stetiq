import { Search } from 'lucide-react'
import { useSearchParams } from 'react-router'
import type { KnowledgeGraphSummary } from '@/api/knowledge-graphs'
import { DataTable } from '@/components/DataTable'
import { PageHeader } from '@/components/PageHeader'
import { Input } from '@/components/ui/input'
import { Skeleton } from '@/components/ui/skeleton'
import { useDataTable } from '@/lib/data-table'
import { setOrDeleteParam } from '@/lib/search-params'
import { knowledgeGraphColumns } from './knowledge-graph-columns'
import { KnowledgeGraphsLoaded } from './KnowledgeGraphsLoaded'

/** `/kg`: every Knowledge Graph the user can read, with its state at a glance. */
export function KnowledgeGraphsPage() {
  return (
    <>
      <PageHeader
        title="Knowledge Graphs"
        description="The Knowledge Graphs you can read, with their Ontology Versions and Construction Runs."
      />
      <KnowledgeGraphsLoaded
        pending={
          <div className="space-y-2">
            <Skeleton className="h-9 w-72" />
            <Skeleton className="h-40 w-full" />
          </div>
        }
      >
        {(data) => <KnowledgeGraphTable data={data} />}
      </KnowledgeGraphsLoaded>
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
      (params) => setOrDeleteParam(params, 'q', value),
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
