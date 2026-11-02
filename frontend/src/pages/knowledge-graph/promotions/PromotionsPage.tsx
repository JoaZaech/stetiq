import { Link } from 'react-router'
import { type Promotion, usePromotions } from '@/api/aliases'
import { knowledgeGraphSection, kgUrl } from '@/app/knowledge-graph-sections'
import { DataTable } from '@/components/DataTable'
import { ErrorAlert } from '@/components/ErrorAlert'
import { StatusLabel } from '@/components/StatusLabel'
import { Skeleton } from '@/components/ui/skeleton'
import { createDataTableColumnHelper, useDataTable } from '@/lib/data-table'
import { formatDateTime } from '@/lib/format'
import { KnowledgeGraphSectionPage } from '../KnowledgeGraphSectionPage'
import { useKnowledgeGraphName } from '../params'

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
  if (result === null) return <StatusLabel tone="neutral" label="Not gated" />
  return result === 'passed' ? (
    <StatusLabel tone="success" label="Passed" />
  ) : (
    <StatusLabel tone="failure" label="Failed" />
  )
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
  const table = useDataTable({
    data,
    columns,
    initialState: { sorting: [{ id: 'promoted_at', desc: true }] },
  })
  return (
    <DataTable
      table={table}
      label="Promotions"
      empty="No Promotions yet. Promote an Ontology Version from its page to move an Alias."
    />
  )
}
