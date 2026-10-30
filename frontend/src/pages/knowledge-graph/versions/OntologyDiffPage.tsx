import { Link } from 'react-router'
import { isNotFound } from '@/api/client'
import { useOntologyDiff } from '@/api/ontology-diff'
import { kgUrl } from '@/app/knowledge-graph-sections'
import { ErrorAlert } from '@/components/ErrorAlert'
import { OntologyDiffView } from '@/components/OntologyDiff'
import { PageHeader } from '@/components/PageHeader'
import { Skeleton } from '@/components/ui/skeleton'
import { NotFoundPage } from '@/pages/NotFoundPage'
import { parseVersionNumber } from '@/lib/version-number'
import { useComparedIds, useKnowledgeGraphName } from '../params'

/**
 * `/kg/:name/versions/compare?id=<base>&id=<target>`: the Ontology Diff between two versions,
 * reached by selecting two rows of the version table. The URL alone reproduces it.
 */
export function OntologyDiffPage() {
  const name = useKnowledgeGraphName()
  const ids = useComparedIds()
  const [base, target] = ids.length === 2 ? ids.map(parseVersionNumber) : []
  const diff = useOntologyDiff(name, base ?? NaN, target ?? NaN)

  if (base === undefined || target === undefined || (diff.isError && isNotFound(diff.error))) {
    return (
      <NotFoundPage
        title="Ontology Version not found"
        message={`Knowledge Graph “${name}” has no Ontology Versions ${ids[0] ?? '?'} and ${ids[1] ?? '?'} to compare.`}
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
