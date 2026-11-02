import { useMemo } from 'react'
import { Link } from 'react-router'
import { type Promotion, usePromotions } from '@/api/aliases'
import { knowledgeGraphSection, kgUrl } from '@/app/knowledge-graph-sections'
import { DataTable } from '@/components/DataTable'
import { ErrorAlert } from '@/components/ErrorAlert'
import { FilterMenu } from '@/components/FilterMenu'
import { ListCount, ListToolbar } from '@/components/ListToolbar'
import { StatusLabel } from '@/components/StatusLabel'
import { Skeleton } from '@/components/ui/skeleton'
import { createDataTableColumnHelper, useDataTable } from '@/lib/data-table'
import { formatDateTime } from '@/lib/format'
import { useSearchParam } from '@/hooks/use-search-param'
import { KnowledgeGraphSectionPage } from '../KnowledgeGraphSectionPage'
import { useKnowledgeGraphName } from '../params'
import { filterPromotions, PROMOTION_GATES, promotionGate } from './promotion-filter'

const SECTION = knowledgeGraphSection('promotions')

function VersionLink({ kg, number }: { kg: string; number: number }) {
  return (
    <Link to={kgUrl(kg, 'versions', String(number))} className="text-primary hover:underline">
      v{number}
    </Link>
  )
}

const column = createDataTableColumnHelper<Promotion>()
const columns = column.columns([
  column.accessor('alias', { header: 'Alias', cell: ({ getValue }) => <span className="font-medium">{getValue()}</span> }),
  column.accessor('from_version', {
    header: 'From',
    sortFn: 'basic',
    sortUndefined: 'first',
    cell: ({ getValue, row }) => {
      const from = getValue()
      return from === null ? (
        <span className="text-muted-foreground">—</span>
      ) : (
        <VersionLink kg={row.original.knowledge_graph} number={from} />
      )
    },
  }),
  column.accessor('to_version', {
    header: 'To',
    sortFn: 'basic',
    cell: ({ getValue, row }) => <VersionLink kg={row.original.knowledge_graph} number={getValue()} />,
  }),
  column.accessor('actor', { header: 'Actor' }),
  column.accessor('promoted_at', {
    header: 'Time',
    sortFn: 'datetime',
    cell: ({ getValue }) => <time dateTime={getValue()}>{formatDateTime(getValue())}</time>,
  }),
  column.accessor('gate_result', {
    header: 'Gate result',
    enableSorting: false,
    cell: ({ getValue }) => <GateResultStatus result={getValue()} />,
  }),
])

/** The version's latest Gate result when it was promoted; "Not gated" when it had none. */
function GateResultStatus({ result }: { result: Promotion['gate_result'] }) {
  const label = promotionGate(result)
  return <StatusLabel tone={result === null ? 'neutral' : result === 'passed' ? 'success' : 'failure'} label={label} />
}

/**
 * `/kg/:name/promotions`: the Promotion audit, newest first. Each move of an Alias
 * with who made it and the version's latest Gate result at that moment.
 */
export function PromotionsPage() {
  return (
    <KnowledgeGraphSectionPage section={SECTION}>
      <PromotionList />
    </KnowledgeGraphSectionPage>
  )
}

function PromotionList() {
  const name = useKnowledgeGraphName()
  const promotions = usePromotions(name)
  if (promotions.isError) return <ErrorAlert error={promotions.error} />
  if (promotions.isPending) return <Skeleton className="h-32 w-full" />
  return <PromotionTable data={promotions.data} />
}

function PromotionTable({ data }: { data: Promotion[] }) {
  const [query, setQuery] = useSearchParam()
  const [gate, setGate] = useSearchParam('gate')
  const shown = useMemo(() => filterPromotions(data, query, gate), [data, query, gate])
  const gateCounts = PROMOTION_GATES.map((g) => [g, data.filter((p) => promotionGate(p.gate_result) === g).length] as const)
  const table = useDataTable({
    data: shown,
    columns,
    initialState: { sorting: [{ id: 'promoted_at', desc: true }] },
  })
  return (
    <div className="space-y-3">
      <ListToolbar search={query} onSearch={setQuery} searchLabel="Search Promotions">
        <FilterMenu label="Gate" value={gate} options={gateCounts} onChange={setGate} />
      </ListToolbar>
      <DataTable
        table={table}
        label="Promotions"
        empty={data.length === 0 ? 'No Promotions yet. Promote a version from its page.' : 'No Promotion matches these filters.'}
      />
      <ListCount shown={shown.length} total={data.length} noun="Promotions" />
    </div>
  )
}
