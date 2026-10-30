import { Outlet, useParams } from 'react-router'
import { useAliases, useContractAlias } from '@/api/aliases'
import { isNotFound } from '@/api/client'
import { useOntologyVersion } from '@/api/ontology-versions'
import { ErrorAlert } from '@/components/ErrorAlert'
import { NeedsEditAccess } from '@/components/NeedsEditAccess'
import { PageHeader } from '@/components/PageHeader'
import { RouteTabs, type RouteTab } from '@/components/RouteTabs'
import { Skeleton } from '@/components/ui/skeleton'
import { NotFoundPage } from '@/pages/NotFoundPage'
import { useKnowledgeGraphName } from '../params'
import { AliasChips } from './AliasChips'
import { aliasesByVersion } from './lineage'
import { PromoteDialog } from './PromoteDialog'

/**
 * The version page's tabs. A tab is a child route of `versions/:number` in
 * `router.tsx` (`''` is the index route); add it there and here. Tab pages read the
 * version with `useOntologyVersionTab()`.
 */
const TABS: readonly RouteTab[] = [
  { label: 'Overview', to: '' },
  { label: 'Ontology', to: 'ontology' },
  { label: 'Changes', to: 'changes' },
]

/** `/kg/:name/versions/:number`: "v{n}" with its Alias chips, then the tabs. */
export function OntologyVersionPage() {
  const name = useKnowledgeGraphName()
  const raw = useParams().number ?? ''
  const number = /^\d+$/.test(raw) ? Number(raw) : NaN
  const version = useOntologyVersion(name, number)

  if (Number.isNaN(number) || (version.isError && isNotFound(version.error))) {
    return (
      <NotFoundPage
        title="Ontology Version not found"
        message={`Knowledge Graph “${name}” has no Ontology Version ${raw}.`}
      />
    )
  }
  if (version.isError) return <ErrorAlert error={version.error} />
  if (version.isPending) return <Skeleton className="h-24 w-full" />
  return (
    <>
      <PageHeader
        title={`v${version.data.number}`}
        description={<VersionAliases name={name} number={version.data.number} />}
        actions={
          <NeedsEditAccess knowledgeGraph={name}>
            {(disabled) => (
              <PromoteDialog name={name} number={version.data.number} disabled={disabled} />
            )}
          </NeedsEditAccess>
        }
      />
      <RouteTabs label="Ontology Version" tabs={TABS} />
      <Outlet context={version.data} />
    </>
  )
}

function VersionAliases({ name, number }: { name: string; number: number }) {
  const aliases = useAliases(name)
  const contractAlias = useContractAlias(name)
  if (!aliases.data) return null
  const names = aliasesByVersion(aliases.data).get(number) ?? []
  return names.length > 0 ? <AliasChips aliases={names} contractAlias={contractAlias.data} /> : null
}
