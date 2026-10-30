import type { ReactNode } from 'react'
import { useAliases, useContractAlias } from '@/api/aliases'
import { useEvolutionMode, useKnowledgeGraph } from '@/api/knowledge-graph'
import { PageHeader } from '@/components/PageHeader'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'

/**
 * Name, description, Evolution Mode and Contract Alias of a Knowledge Graph: the top of
 * every Knowledge Graph section page. Edit actions (e.g. the description editor) go in
 * `PageHeader`'s `actions`.
 */
export function KnowledgeGraphHeader({ name }: { name: string }) {
  const kg = useKnowledgeGraph(name)
  const description = kg.data?.description
  return (
    <section aria-label="Knowledge Graph" className="mb-6">
      <PageHeader
        title={name}
        description={description ? description : <span className="italic">No description</span>}
      />
      <dl className="-mt-3 flex flex-wrap gap-x-8 gap-y-2 text-sm">
        <Fact label="Evolution Mode">
          <EvolutionModeValue name={name} />
        </Fact>
        <Fact label="Contract Alias">
          <ContractAliasValue name={name} />
        </Fact>
      </dl>
    </section>
  )
}

function Fact({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex items-center gap-2">
      <dt className="text-muted-foreground">{label}</dt>
      <dd>{children}</dd>
    </div>
  )
}

function EvolutionModeValue({ name }: { name: string }) {
  const mode = useEvolutionMode(name)
  if (mode.isPending) return <Skeleton className="h-5 w-16" />
  if (mode.isError) return <span className="text-destructive">unavailable</span>
  return <Badge variant="outline">{mode.data}</Badge>
}

function ContractAliasValue({ name }: { name: string }) {
  const contract = useContractAlias(name)
  const aliases = useAliases(name)
  if (contract.isPending || aliases.isPending) return <Skeleton className="h-5 w-28" />
  if (contract.isError || aliases.isError) return <span className="text-destructive">unavailable</span>
  const alias = aliases.data.find((a) => a.name === contract.data)
  return (
    <Badge>
      {alias ? `${alias.name} → v${alias.version}` : `${contract.data} (not set)`}
    </Badge>
  )
}
