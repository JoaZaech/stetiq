import { ViewToggle } from '@/components/ViewToggle'
import { useComparisonView } from './comparison-view'
import { MAP_VIEW_OPTIONS } from './map-view'
import { OntologyComparisonMap } from './OntologyComparisonMap'
import { OntologyComparisonTable } from './OntologyComparisonTable'
import { useOntologyVersionTab } from './version-context'

/**
 * The version page's Changes tab, against the previous version: both versions superimposed
 * on a Map (`?view=` absent), or its changes as a grid (`?view=table`).
 */
export function ChangesTab() {
  const version = useOntologyVersionTab()
  const [view, setView] = useComparisonView()
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
        <ViewToggle options={MAP_VIEW_OPTIONS} mode={view} onChange={setView} />
      </div>
      {view === 'map' ? (
        <OntologyComparisonMap knowledgeGraph={version.knowledge_graph} base={base} target={version.number} />
      ) : (
        <OntologyComparisonTable knowledgeGraph={version.knowledge_graph} base={base} target={version.number} />
      )}
    </div>
  )
}
