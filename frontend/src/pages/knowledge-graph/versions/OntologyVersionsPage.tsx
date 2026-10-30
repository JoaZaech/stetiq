import { useMemo } from 'react'
import { Link } from 'react-router'
import {
  type Alias,
  type Promotion,
  useAliases,
  useContractAlias,
  usePromotions,
} from '@/api/aliases'
import { useOntologyVersions, type OntologyVersion } from '@/api/ontology-versions'
import { knowledgeGraphSection, kgUrl } from '@/app/knowledge-graph-sections'
import { DataTable } from '@/components/DataTable'
import { ErrorAlert } from '@/components/ErrorAlert'
import { Skeleton } from '@/components/ui/skeleton'
import { createDataTableColumnHelper, useDataTable } from '@/lib/data-table'
import { formatDateTime } from '@/lib/format'
import { KnowledgeGraphSectionPage } from '../KnowledgeGraphSectionPage'
import { useKnowledgeGraphName } from '../params'
import { AliasChips, CandidateBadge } from './AliasChips'
import { aliasesByVersion, candidateVersions } from './lineage'

const SECTION = knowledgeGraphSection('versions')

/** One row of the version table. */
interface VersionRow {
  knowledgeGraph: string
  number: number
  origin: OntologyVersion['origin']
  createdAt: string
  aliases: string[]
  contractAlias: string | undefined
  candidate: boolean
}

const column = createDataTableColumnHelper<VersionRow>()

const columns = column.columns([
  column.accessor('number', {
    header: 'Version',
    cell: ({ row }) => (
      <Link
        to={kgUrl(row.original.knowledgeGraph, 'versions', row.original.number)}
        className="font-medium text-primary underline-offset-4 hover:underline"
      >
        v{row.original.number}
      </Link>
    ),
  }),
  column.accessor('origin', { header: 'Origin' }),
  column.accessor('createdAt', {
    header: 'Created',
    sortFn: 'datetime',
    cell: ({ getValue }) => <time dateTime={getValue()}>{formatDateTime(getValue())}</time>,
  }),
  column.display({
    id: 'aliases',
    header: 'Aliases',
    cell: ({ row }) => (
      <span className="inline-flex flex-wrap items-center gap-1">
        <AliasChips aliases={row.original.aliases} contractAlias={row.original.contractAlias} />
        {row.original.candidate && <CandidateBadge />}
      </span>
    ),
  }),
])

/** `/kg/:name/versions`: the Knowledge Graph's Ontology Versions, newest first. */
export function OntologyVersionsPage() {
  return (
    <KnowledgeGraphSectionPage section={SECTION}>
      <VersionList />
    </KnowledgeGraphSectionPage>
  )
}

function VersionList() {
  const name = useKnowledgeGraphName()
  const versions = useOntologyVersions(name)
  const aliases = useAliases(name)
  const promotions = usePromotions(name)
  const contractAlias = useContractAlias(name)

  if (versions.isError || aliases.isError || promotions.isError) {
    return <ErrorAlert error={versions.error ?? aliases.error ?? promotions.error} />
  }
  if (versions.isPending || aliases.isPending || promotions.isPending) {
    return <Skeleton className="h-32 w-full" />
  }
  if (versions.data.length === 0) {
    return <p className="text-sm text-muted-foreground">No Ontology Versions yet.</p>
  }
  return (
    <VersionTable
      name={name}
      versions={versions.data}
      aliases={aliases.data}
      promotions={promotions.data}
      contractAlias={contractAlias.data}
    />
  )
}

function VersionTable({
  name,
  versions,
  aliases,
  promotions,
  contractAlias,
}: {
  name: string
  versions: OntologyVersion[]
  aliases: Alias[]
  promotions: Promotion[]
  contractAlias: string | undefined
}) {
  // Rows stay referentially stable between renders, as `useDataTable` needs.
  const data = useMemo(() => {
    const aliased = aliasesByVersion(aliases)
    const candidates = candidateVersions(versions, promotions)
    return versions.map(
      (v): VersionRow => ({
        knowledgeGraph: name,
        number: v.number,
        origin: v.origin,
        createdAt: v.created_at,
        aliases: aliased.get(v.number) ?? [],
        contractAlias,
        candidate: candidates.has(v.number),
      }),
    )
  }, [name, versions, aliases, promotions, contractAlias])
  const table = useDataTable({
    data,
    columns,
    initialState: { sorting: [{ id: 'number', desc: true }] },
  })
  return <DataTable table={table} label="Ontology Versions" empty="No Ontology Versions yet." />
}
