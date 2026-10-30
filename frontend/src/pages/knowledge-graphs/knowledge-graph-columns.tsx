import { Link } from 'react-router'
import type { KnowledgeGraphSummary } from '@/api/knowledge-graphs'
import { RunStatusLabel } from '@/components/RunStatusLabel'
import { createDataTableColumnHelper } from '@/lib/data-table'
import { formatDateTime } from '@/lib/format'

const column = createDataTableColumnHelper<KnowledgeGraphSummary>()
const version = (n: number | null | undefined) => (n == null ? '—' : `v${n}`)

/** The columns of every Knowledge Graph table: the list page and Home's recent ones. */
export const knowledgeGraphColumns = column.columns([
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
