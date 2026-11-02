import { useId } from 'react'
import {
  CircleDot,
  GitMerge,
  MessageSquare,
  Plug,
  ShieldCheck,
  Webhook,
  Workflow,
  type LucideIcon,
} from 'lucide-react'
import type { Consumer } from '@/api/use-cases'
import { Planned, PlannedBadge } from '@/components/Planned'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog'

interface ExampleConnector {
  name: string
  /** A generic icon: the picker shows no brand logos. */
  icon: LucideIcon
  /** One line on what it would do. */
  does: string
}

/**
 * The example tools a Connector could link a Consumer through, grouped by what a Connector
 * does, as `docs/vision.md` › Connector lists them. None is built; each would run at the
 * Consumer's edge, never in the core (ADR 0005).
 */
const EXAMPLE_CONNECTORS: { group: string; connectors: ExampleConnector[] }[] = [
  {
    group: 'Enforce in CI',
    connectors: [
      {
        name: 'GitHub Actions',
        icon: Workflow,
        does: "Fails the pull request that bumps the Consumer's Ontology Version when its Consumer Gate fails.",
      },
      {
        name: 'GitLab CI',
        icon: GitMerge,
        does: "Fails the merge request that bumps the Consumer's Ontology Version when its Consumer Gate fails.",
      },
    ],
  },
  {
    group: 'Get notified',
    connectors: [
      {
        name: 'Webhook',
        icon: Webhook,
        does: "Receives a signed event at the Consumer's own URL when an Ontology change affects its Tasks.",
      },
      {
        name: 'Slack',
        icon: MessageSquare,
        does: "Tells the Consumer's team in its channel when an Ontology change affects its Tasks.",
      },
      {
        name: 'GitHub Issues',
        icon: CircleDot,
        does: "Opens an issue in the Consumer's repository when an Ontology change affects its Tasks.",
      },
    ],
  },
  {
    group: "In the Consumer's code",
    connectors: [
      {
        name: 'LangChain',
        icon: ShieldCheck,
        does: 'A guard that asks for a Consumer Gate verdict before an agent uses a new Ontology Version.',
      },
      {
        name: 'LlamaIndex',
        icon: ShieldCheck,
        does: 'A guard that asks for a Consumer Gate verdict before an agent or query engine uses a new Ontology Version.',
      },
    ],
  },
]

/**
 * A Consumer tile's Connect button, badged Planned, and the picker it opens: the example
 * Connectors, each a disabled stand-in. Nothing here is wired up.
 */
export function ConnectorPicker({ consumer }: { consumer: Consumer }) {
  return (
    <span className="inline-flex items-center gap-1.5">
      <Dialog>
        <DialogTrigger asChild>
          <Button size="sm" variant="outline">
            <Plug />
            Connect
          </Button>
        </DialogTrigger>
        <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-2xl">
          <DialogHeader>
            <DialogTitle>Connect {consumer.name}</DialogTitle>
            <DialogDescription>
              Example tools a Connector could link this Consumer through. Each would run at the Consumer's
              edge; none is built yet.
            </DialogDescription>
          </DialogHeader>
          {EXAMPLE_CONNECTORS.map(({ group, connectors }) => (
            <ConnectorGroup key={group} group={group} connectors={connectors} />
          ))}
        </DialogContent>
      </Dialog>
      <PlannedBadge
        label="Connect"
        section="connector"
        tooltip="A Connector will link this Consumer to stetiq from its own edge: it tells the Consumer's team about Ontology changes that affect its Tasks and enforces its Consumer Gate."
      />
    </span>
  )
}

function ConnectorGroup({ group, connectors }: { group: string; connectors: ExampleConnector[] }) {
  const headingId = useId()
  return (
    <section aria-labelledby={headingId} className="space-y-2">
      <h3 id={headingId} className="text-sm font-medium">
        {group}
      </h3>
      <ul className="grid gap-2 sm:grid-cols-2">
        {connectors.map((connector) => (
          <li key={connector.name} className="min-w-0">
            <ConnectorTile connector={connector} />
          </li>
        ))}
      </ul>
    </section>
  )
}

function ConnectorTile({ connector }: { connector: ExampleConnector }) {
  const titleId = useId()
  const Icon = connector.icon
  return (
    <article
      aria-labelledby={titleId}
      className="flex h-full min-w-0 gap-3 rounded-lg p-3 text-sm ring-1 ring-foreground/10"
    >
      <span className="flex size-8 shrink-0 items-center justify-center rounded-md bg-muted">
        <Icon aria-hidden className="size-4 text-muted-foreground" />
      </span>
      <div className="min-w-0 flex-1 space-y-1">
        <h4 id={titleId} className="font-semibold">
          {connector.name}
        </h4>
        <p className="text-muted-foreground">{connector.does}</p>
        <Planned
          label={connector.name}
          section="connector"
          tooltip={`A Connector through ${connector.name}, run at the Consumer's edge.`}
          className="pt-1"
        >
          <Button size="sm" variant="outline" disabled>
            Connect
          </Button>
        </Planned>
      </div>
    </article>
  )
}
