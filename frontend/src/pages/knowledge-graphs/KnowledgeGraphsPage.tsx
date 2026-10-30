import { Search } from 'lucide-react'
import { Link, useSearchParams } from 'react-router'
import { type KnowledgeGraph, useKnowledgeGraphs } from '@/api/knowledge-graphs'
import { DataTable } from '@/components/DataTable'
import { ErrorAlert } from '@/components/ErrorAlert'
import { PageHeader } from '@/components/PageHeader'
import { RunStatusLabel } from '@/components/RunStatusLabel'
import { Input } from '@/components/ui/input'
import { Skeleton } from '@/components/ui/skeleton'
import { createDataTableColumnHelper, useDataTable } from '@/lib/data-table'
import { formatDateTime } from '@/lib/format'

const column = createDataTableColumnHelper<KnowledgeGraph>()
const version = (n: number | null | undefined) => (n == null ? '—' : `v${n}`)

const columns = column.columns([
  column.accessor('name', {
    header: 'Name',
    filterFn: 'includesString',
    cell: ({ getValue }) => (
      <Link
        to={`/kg/${encodeURIComponent(getValue())}`}
        className="font-medium text-primary hover:underline"
      >
        {getValue()}
      </Link>
    ),
  }),
  column.accessor('contract_version', {
    header: 'Contract Alias version',
    cell: ({ getValue }) => version(getValue()),
  }),
  column.accessor('latest_version', {
    header: 'Latest version',
    cell: ({ getValue }) => version(getValue()),
  }),
  column.accessor('last_run_status', {
    header: 'Last run',
    enableSorting: false,
    cell: ({ getValue }) => {
      const status = getValue()
      return status ? <RunStatusLabel status={status} /> : <span className="text-muted-foreground">No runs</span>
    },
  }),
  column.accessor('last_modified_at', {
    header: 'Last modified',
    sortFn: 'datetime',
    cell: ({ getValue }) => {
      const at = getValue()
      return at ? <time dateTime={at}>{formatDateTime(at)}</time> : '—'
    },
  }),
])

/** The landing page: every Knowledge Graph the user can read, with its state at a glance. */
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
        <EmptyState />
      ) : (
        <KnowledgeGraphTable data={knowledgeGraphs.data} />
      )}
    </>
  )
}

function KnowledgeGraphTable({ data }: { data: KnowledgeGraph[] }) {
  // The search lives in the URL (?q=), so a filtered list can be shared.
  const [searchParams, setSearchParams] = useSearchParams()
  const search = searchParams.get('q') ?? ''
  const table = useDataTable({
    data,
    columns,
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

const SNIPPET = `from pathlib import Path

import stetiq

client = stetiq.Client()  # or stetiq.Client("http://<server>") with $STETIQ_TOKEN
client.create_knowledge_graph("support", ontology=Path("ontology.yaml"))`

/** No Knowledge Graph at all: show how to register the first Ontology Version. */
function EmptyState() {
  return (
    <div className="rounded-lg border border-dashed p-8">
      <h2 className="text-base font-semibold">No Knowledge Graphs yet</h2>
      <p className="mt-1 max-w-prose text-sm text-muted-foreground">
        Create one from the Python SDK. Its Declared Ontology becomes Ontology Version 1 and the
        Contract Alias <code className="font-mono">production</code> points to it.
      </p>
      <pre className="mt-4 overflow-x-auto rounded-md bg-muted p-4 text-sm">
        <code className="font-mono">{SNIPPET}</code>
      </pre>
    </div>
  )
}
