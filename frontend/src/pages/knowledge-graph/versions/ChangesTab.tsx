import { Network, Table2 } from 'lucide-react'
import { OntologyDiffPanel } from '@/components/OntologyDiff'
import { ViewToggle, type ViewOption } from '@/components/ViewToggle'
import { useViewParam } from '@/lib/view-param'
import { OntologyComparisonMap } from './OntologyComparisonMap'
import { useOntologyVersionTab } from './version-context'

type ChangesView = 'table' | 'map'

const VIEWS: readonly [ChangesView, ...ChangesView[]] = ['table', 'map']

const VIEW_OPTIONS: readonly ViewOption<ChangesView>[] = [
  { value: 'table', label: 'Table', icon: Table2 },
  { value: 'map', label: 'Map', icon: Network },
]

/**
 * The version page's Changes tab, against the previous version: the Ontology Diff as a
 * list (`?view=` absent), or both versions superimposed on a Map (`?view=map`).
 */
export function ChangesTab() {
  const version = useOntologyVersionTab()
  const [view, setView] = useViewParam(VIEWS)
  if (version.number === 1) {
    return (
      <p className="text-sm text-muted-foreground">
        v1 is the first Ontology Version: there is nothing to compare it with.
      </p>
    )
  }
  const base = version.number - 1
  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-4">
        <p className="text-sm text-muted-foreground">Changes from v{base}</p>
        <ViewToggle options={VIEW_OPTIONS} mode={view} onChange={setView} />
      </div>
      {view === 'map' ? (
        <OntologyComparisonMap knowledgeGraph={version.knowledge_graph} base={base} target={version.number} />
      ) : (
        <OntologyDiffPanel knowledgeGraph={version.knowledge_graph} base={base} target={version.number} />
      )}
    </div>
  )
}
