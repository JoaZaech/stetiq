import { Link } from 'react-router'
import { isNotFound } from '@/api/client'
import { useOntologyDiff } from '@/api/ontology-diff'
import { kgUrl } from '@/app/knowledge-graph-sections'
import { ErrorAlert } from '@/components/ErrorAlert'
import { PageHeader } from '@/components/PageHeader'
import { NotFoundPage } from '@/pages/NotFoundPage'
import { parseVersionNumber } from '@/lib/version-number'
import { useComparedIds, useKnowledgeGraphName } from '../../params'
import { useComparisonView } from './comparison-view'
import { useMapViewControls } from '../map-view-controls'
import { OntologyComparisonMap } from './OntologyComparisonMap'
import { OntologyComparisonTable } from './OntologyComparisonTable'

/**
 * `/kg/:name/versions/compare?id=<base>&id=<target>`: the Ontology Diff between two versions,
 * reached by selecting two rows of the version table, as both versions superimposed on a
 * Map or, at `&view=table`, as a grid of its changes, whose sort, filters and search
 * (`?changes.…`) sit beside the chosen versions. The URL alone reproduces it.
 */
export function OntologyDiffPage() {
  const name = useKnowledgeGraphName()
  const ids = useComparedIds()
  const [view, setView] = useComparisonView()
  const { controls, filtersIn } = useMapViewControls(view, setView)
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
        actions={controls}
      />
      {diff.isError ? (
        <ErrorAlert error={diff.error} />
      ) : view === 'map' ? (
        <OntologyComparisonMap knowledgeGraph={name} base={base} target={target} filtersIn={filtersIn} />
      ) : (
        <OntologyComparisonTable knowledgeGraph={name} base={base} target={target} />
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
