import { Link, useSearchParams } from 'react-router'
import { isNotFound } from '@/api/client'
import { useOntologyDiff } from '@/api/ontology-diff'
import { kgUrl } from '@/app/knowledge-graph-sections'
import { ErrorAlert } from '@/components/ErrorAlert'
import { OntologyDiffView } from '@/components/OntologyDiff'
import { PageHeader } from '@/components/PageHeader'
import { Skeleton } from '@/components/ui/skeleton'
import { NotFoundPage } from '@/pages/NotFoundPage'
import { useKnowledgeGraphName } from '../params'

const versionNumber = (raw: string | null) =>
  raw !== null && /^\d+$/.test(raw) ? Number(raw) : NaN

/**
 * `/kg/:name/versions/compare?base=&target=`: the Ontology Diff between two versions,
 * reached by selecting two rows of the version table. The URL alone reproduces it.
 */
export function OntologyDiffPage() {
  const name = useKnowledgeGraphName()
  const [params] = useSearchParams()
  const base = versionNumber(params.get('base'))
  const target = versionNumber(params.get('target'))
  const valid = Number.isInteger(base) && Number.isInteger(target)
  const diff = useOntologyDiff(name, base, target)

  if (!valid || (diff.isError && isNotFound(diff.error))) {
    return (
      <NotFoundPage
        title="Ontology Version not found"
        message={`Knowledge Graph “${name}” has no Ontology Versions ${params.get('base') ?? '?'} and ${params.get('target') ?? '?'} to compare.`}
      />
    )
  }
  return (
    <>
      <PageHeader
        title={`Compare v${base} → v${target}`}
        description={
          <>
            The Ontology Diff from <VersionLink name={name} number={base} /> to{' '}
            <VersionLink name={name} number={target} />.
          </>
        }
      />
      {diff.isError ? (
        <ErrorAlert error={diff.error} />
      ) : diff.isPending ? (
        <Skeleton className="h-32 w-full" />
      ) : (
        <OntologyDiffView diff={diff.data} base={base} target={target} />
      )}
    </>
  )
}

function VersionLink({ name, number }: { name: string; number: number }) {
  return (
    <Link
      to={kgUrl(name, 'versions', number)}
      className="font-medium text-primary underline-offset-4 hover:underline"
    >
      v{number}
    </Link>
  )
}
