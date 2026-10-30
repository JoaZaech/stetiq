import { useSearchParams } from 'react-router'
import type { KnowledgeGraphSummary } from '@/api/knowledge-graphs'
import { DataTable } from '@/components/DataTable'
import { PageHeader } from '@/components/PageHeader'
import { SearchInput } from '@/components/SearchInput'
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
      <SearchInput label="Search Knowledge Graphs" placeholder="Search by name" value={search} onChange={setSearch} />
      <DataTable table={table} empty={`No Knowledge Graph matches “${search}”`} />
    </div>
  )
}
