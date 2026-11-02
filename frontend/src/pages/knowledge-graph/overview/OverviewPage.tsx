import { useId } from 'react'
import { useEvolutionMode, useKnowledgeGraph } from '@/api/knowledge-graph'
import { Markdown } from '@/components/Markdown'
import { PageHeader } from '@/components/PageHeader'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import { EditDescription } from '../KnowledgeGraphHeader'
import { useKnowledgeGraphName } from '../params'
import { PipelineStrip } from './PipelineStrip'

/**
 * `/kg/:name/overview`, where a Knowledge Graph opens: the pipeline strip as a status
 * chain, then what the Knowledge Graph is (its description and Evolution Mode). Unlike the
 * other sections it has no one-line header: the Contract Alias is on the chain.
 */
export function OverviewPage() {
  const name = useKnowledgeGraphName()
  return (
    <>
      <PageHeader title={name} />
      <div className="space-y-8">
        <PipelineStrip name={name} />
        <About name={name} />
      </div>
    </>
  )
}

function About({ name }: { name: string }) {
  const id = useId()
  const description = useKnowledgeGraph(name).data?.description
  return (
    <section aria-labelledby={id} className="max-w-3xl space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 id={id} className="text-base font-semibold">
          About
        </h2>
        <EditDescription name={name} />
      </div>
      <div className="text-muted-foreground">
        {description ? <Markdown>{description}</Markdown> : <p className="text-sm italic">No description</p>}
      </div>
      <dl className="flex items-center gap-2 text-sm">
        <dt className="text-muted-foreground">Evolution Mode</dt>
        <dd>
          <EvolutionModeValue name={name} />
        </dd>
      </dl>
    </section>
  )
}

function EvolutionModeValue({ name }: { name: string }) {
  const mode = useEvolutionMode(name)
  if (mode.isPending) return <Skeleton className="h-5 w-16" />
  if (mode.isError) return <span className="text-destructive">unavailable</span>
  return <Badge variant="outline">{mode.data}</Badge>
}
