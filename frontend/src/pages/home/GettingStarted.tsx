import { ChevronDown } from 'lucide-react'
import { useId, useState } from 'react'
import { Link } from 'react-router'
import { readStored, writeStored } from '@/lib/local-storage'
import { cn } from '@/lib/utils'
import { helpUrl } from '@/pages/help/guide-index'

/**
 * One card per step of the workflow, each opening the user-guide page about it. The guide
 * is organised by tool, so the steps link to their section of the Concepts page.
 */
const STEPS = [
  {
    title: 'Declare an Ontology',
    description: 'Create a Knowledge Graph from a Declared Ontology and version it.',
    to: `${helpUrl('concepts')}#knowledge-graphs-and-ontology-versions`,
  },
  {
    title: 'Construction Runs',
    description: 'Track each build of the graph and check it conforms to its Ontology Version.',
    to: `${helpUrl('concepts')}#construction-runs-and-conformance`,
  },
  {
    title: 'Use Cases & Evaluation',
    description: 'Write Competency Questions and judge Ontology Versions with Evaluators.',
    to: `${helpUrl('concepts')}#evaluators-and-use-cases`,
  },
  {
    title: 'Observations & Drift',
    description: 'Observe the live graph and catch Drift from its Ontology Version.',
    to: `${helpUrl('concepts')}#observation-and-drift`,
  },
  {
    title: 'Promotions & Aliases',
    description: 'Move Aliases such as production to a new Ontology Version, behind Gates.',
    to: `${helpUrl('concepts')}#aliases-and-promotion`,
  },
]

const COLLAPSED_KEY = 'stetiq.home.getting-started-collapsed'

/** Home's Getting Started block. Collapsing it is remembered per browser. */
export function GettingStarted() {
  const [collapsed, setCollapsed] = useState(() => readStored(COLLAPSED_KEY) === 'true')
  const headingId = useId()
  const contentId = useId()

  const toggle = () => {
    setCollapsed(!collapsed)
    writeStored(COLLAPSED_KEY, String(!collapsed))
  }

  return (
    <section aria-labelledby={headingId} className="space-y-3">
      <h2 id={headingId} className="text-base font-semibold">
        <button
          type="button"
          aria-expanded={!collapsed}
          aria-controls={contentId}
          onClick={toggle}
          className="flex items-center gap-1.5 rounded-sm hover:text-primary focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
        >
          <ChevronDown aria-hidden className={cn('size-4 transition-transform', collapsed && '-rotate-90')} />
          Getting Started
        </button>
      </h2>
      {!collapsed && (
        <ul id={contentId} className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
          {STEPS.map((step) => (
            <li key={step.title}>
              <Link
                to={step.to}
                className="block h-full rounded-lg border bg-card p-4 transition-colors hover:border-primary hover:bg-accent focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
              >
                <h3 className="text-sm font-semibold">{step.title}</h3>
                <p className="mt-1 text-sm text-muted-foreground">{step.description}</p>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
