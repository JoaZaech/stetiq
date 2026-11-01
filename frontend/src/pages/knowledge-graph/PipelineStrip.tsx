import type { ReactNode } from 'react'
import { ChevronRight } from 'lucide-react'
import { Link } from 'react-router'
import { useUseCaseVersions } from '@/api/use-cases'
import { kgUrl } from '@/app/knowledge-graph-sections'
import { Planned } from '@/components/Planned'
import { Skeleton } from '@/components/ui/skeleton'
import { cn } from '@/lib/utils'

/**
 * Where a Knowledge Graph sits (docs/vision.md, "The two-gate pipeline"): upstream
 * pipeline → Gate → Knowledge Graph → Consumer Gate → Consumers. Live parts are drawn in
 * normal emphasis; the Consumer Gate is planned, so it is muted and badged. Wraps onto
 * more lines on a narrow screen.
 */
export function PipelineStrip({ name }: { name: string }) {
  const steps: { key: string; planned?: boolean; content: ReactNode }[] = [
    { key: 'upstream', content: 'Upstream pipeline' },
    { key: 'gate', content: 'Gate' },
    { key: 'kg', content: <span className="font-medium">Knowledge Graph</span> },
    {
      key: 'consumer-gate',
      planned: true,
      content: (
        <Planned
          label="Consumer Gate"
          section="the-two-gate-pipeline"
          tooltip="A rule, one per Consumer, that must hold for that Consumer to take an Ontology Version."
        >
          Consumer Gate
        </Planned>
      ),
    },
    { key: 'consumers', content: <ConsumersStep name={name} /> },
  ]
  return (
    <ol aria-label="Pipeline" className="flex min-w-0 flex-wrap items-center gap-y-2 text-sm">
      {steps.map(({ key, planned, content }, i) => (
        <li key={key} className="inline-flex items-center">
          {i > 0 && <ChevronRight aria-hidden className="mx-1 size-4 shrink-0 text-muted-foreground" />}
          <span className={cn('rounded-md border px-2 py-0.5', planned && 'border-dashed')}>{content}</span>
        </li>
      ))}
    </ol>
  )
}

/** The Consumers declared in the latest Use Case Version, linking to the Use Case page. */
function ConsumersStep({ name }: { name: string }) {
  const versions = useUseCaseVersions(name)
  const count = versions.data?.at(-1)?.use_case.consumers?.length ?? 0
  return (
    <Link to={kgUrl(name, 'use-case')} className="inline-flex items-center gap-1.5 hover:underline">
      Consumers{' '}
      {versions.isPending ? (
        <Skeleton className="h-4 w-4" />
      ) : (
        !versions.isError && <span className="tabular-nums text-muted-foreground">{count}</span>
      )}
    </Link>
  )
}
