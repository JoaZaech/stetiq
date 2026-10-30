import { Link } from 'react-router'
import { useAliases, useContractAlias, usePromotions } from '@/api/aliases'
import { useOntologyVersions } from '@/api/ontology-versions'
import { knowledgeGraphSection, kgUrl } from '@/app/knowledge-graph-sections'
import { ErrorAlert } from '@/components/ErrorAlert'
import { Skeleton } from '@/components/ui/skeleton'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { formatDateTime } from '@/lib/format'
import { KnowledgeGraphSectionPage } from '../KnowledgeGraphSectionPage'
import { useKnowledgeGraphName } from '../params'
import { AliasChips, CandidateBadge } from './AliasChips'
import { aliasesByVersion, candidateVersions } from './lineage'

const SECTION = knowledgeGraphSection('versions')

/** `/kg/:name/versions`: the Knowledge Graph's Ontology Versions, newest first. */
export function OntologyVersionsPage() {
  return (
    <KnowledgeGraphSectionPage section={SECTION}>
      <VersionTable />
    </KnowledgeGraphSectionPage>
  )
}

function VersionTable() {
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

  const aliased = aliasesByVersion(aliases.data)
  const candidates = candidateVersions(versions.data, promotions.data)
  const newestFirst = [...versions.data].sort((a, b) => b.number - a.number)
  return (
    <Table aria-label="Ontology Versions">
      <TableHeader>
        <TableRow>
          <TableHead>Version</TableHead>
          <TableHead>Origin</TableHead>
          <TableHead>Created</TableHead>
          <TableHead>Aliases</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {newestFirst.map((v) => (
          <TableRow key={v.number}>
            <TableCell className="font-medium">
              <Link
                to={kgUrl(name, 'versions', v.number)}
                className="text-primary underline-offset-4 hover:underline"
              >
                v{v.number}
              </Link>
            </TableCell>
            <TableCell>{v.origin}</TableCell>
            <TableCell>{formatDateTime(v.created_at)}</TableCell>
            <TableCell>
              <span className="inline-flex flex-wrap items-center gap-1">
                <AliasChips aliases={aliased.get(v.number) ?? []} contractAlias={contractAlias.data} />
                {candidates.has(v.number) && <CandidateBadge />}
              </span>
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  )
}
