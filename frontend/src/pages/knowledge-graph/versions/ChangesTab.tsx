import { OntologyDiffPanel } from '@/components/OntologyDiff'
import { useOntologyVersionTab } from './version-context'

/** The version page's Changes tab: the Ontology Diff against the previous version. */
export function ChangesTab() {
  const version = useOntologyVersionTab()
  if (version.number === 1) {
    return (
      <p className="text-sm text-muted-foreground">
        v1 is the first Ontology Version: there is nothing to compare it with.
      </p>
    )
  }
  return (
    <OntologyDiffPanel
      knowledgeGraph={version.knowledge_graph}
      base={version.number - 1}
      target={version.number}
      caption={`Changes from v${version.number - 1}`}
    />
  )
}
