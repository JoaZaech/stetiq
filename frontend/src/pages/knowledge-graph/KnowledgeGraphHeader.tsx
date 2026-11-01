import { useAliases, useContractAlias } from '@/api/aliases'
import { useKnowledgeGraph } from '@/api/knowledge-graph'
import { NeedsEditAccess } from '@/components/NeedsEditAccess'
import { PageHeader } from '@/components/PageHeader'
import { Skeleton } from '@/components/ui/skeleton'
import { EditDescriptionDialog } from './EditDescriptionDialog'
import { contractAliasLabel } from './overview/pipeline-status'
import { ContractAliasChip } from './versions/AliasChips'

/**
 * The one-line top of every Knowledge Graph section page but the Overview: the name, the
 * Contract Alias chip and Edit description. The description, the Evolution Mode and the
 * pipeline strip are on the Overview.
 */
export function KnowledgeGraphHeader({ name }: { name: string }) {
  return (
    <section aria-label="Knowledge Graph">
      <PageHeader title={name} aside={<ContractAliasValue name={name} />} actions={<EditDescription name={name} />} />
    </section>
  )
}

/** Edit description, disabled without edit access. */
export function EditDescription({ name }: { name: string }) {
  const kg = useKnowledgeGraph(name)
  return (
    <NeedsEditAccess knowledgeGraph={name}>
      {(disabled) => (
        <EditDescriptionDialog name={name} description={kg.data?.description ?? null} disabled={disabled} />
      )}
    </NeedsEditAccess>
  )
}

function ContractAliasValue({ name }: { name: string }) {
  const contract = useContractAlias(name)
  const aliases = useAliases(name)
  if (contract.isPending || aliases.isPending) return <Skeleton className="h-5 w-28" />
  if (contract.isError || aliases.isError) return <span className="text-sm text-destructive">Contract Alias unavailable</span>
  const alias = aliases.data.find((a) => a.name === contract.data)
  return <ContractAliasChip alias={contractAliasLabel(contract.data, alias?.version)} />
}
