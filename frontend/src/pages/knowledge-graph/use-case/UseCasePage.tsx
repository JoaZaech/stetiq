import { useId, type ReactNode } from 'react'
import { useUseCaseVersions, type UseCaseVersion } from '@/api/use-cases'
import { knowledgeGraphSection } from '@/app/knowledge-graph-sections'
import { ErrorAlert } from '@/components/ErrorAlert'
import { Skeleton } from '@/components/ui/skeleton'
import { formatDateTime } from '@/lib/format'
import { KnowledgeGraphSectionPage } from '../KnowledgeGraphSectionPage'
import { useKnowledgeGraphName } from '../params'
import { CompetencyQuestionsTable } from './CompetencyQuestionsTable'
import { UseCaseVersionsTable } from './UseCaseVersionsTable'

const SECTION = knowledgeGraphSection('use-case')

/**
 * `/kg/:name/use-case`: the latest Use Case Version (description and Competency
 * Questions), then every Use Case Version, to compare.
 *
 * Competency Question editing (#33) plugs in here: an "Add Competency Question" button
 * in the section's `actions`, and Edit / Remove per question through
 * `CompetencyQuestionsTable`'s `rowActions`. Both act on the latest version's Use Case.
 */
export function UseCasePage() {
  return (
    <KnowledgeGraphSectionPage section={SECTION}>
      <UseCase />
    </KnowledgeGraphSectionPage>
  )
}

function UseCase() {
  const name = useKnowledgeGraphName()
  const versions = useUseCaseVersions(name)

  if (versions.isError) return <ErrorAlert error={versions.error} />
  if (versions.isPending) return <Skeleton className="h-32 w-full" />
  const latest = versions.data.at(-1)
  if (!latest) {
    return (
      <p className="rounded-lg border border-dashed p-6 text-sm text-muted-foreground">
        No Use Case has been registered yet. Register one with{' '}
        <code className="font-mono text-xs">client.register_use_case("{name}", …)</code>.
      </p>
    )
  }
  return (
    <div className="space-y-8">
      <LatestVersion version={latest} />
      <Panel title="Use Case Versions">
        <UseCaseVersionsTable name={name} versions={versions.data} />
      </Panel>
    </div>
  )
}

function LatestVersion({ version }: { version: UseCaseVersion }) {
  return (
    <Panel title={`Use Case Version ${version.number}`}>
      <p className="text-xs text-muted-foreground">
        Latest, created {formatDateTime(version.created_at)}
      </p>
      <p className="text-sm">
        {version.use_case.description ?? <span className="text-muted-foreground">No description</span>}
      </p>
      <CompetencyQuestionsTable questions={version.use_case.competency_questions} />
    </Panel>
  )
}

function Panel({ title, children }: { title: string; children: ReactNode }) {
  const id = useId()
  return (
    <section aria-labelledby={id} className="min-w-0 space-y-3">
      <h3 id={id} className="text-sm font-semibold">
        {title}
      </h3>
      {children}
    </section>
  )
}
