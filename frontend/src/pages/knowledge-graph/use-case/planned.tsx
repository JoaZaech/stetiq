import { Sparkles } from 'lucide-react'
import { Planned } from '@/components/Planned'
import { Button } from '@/components/ui/button'

/** A Consumer card's planned edge: its Connector (docs/vision.md). CI enforces its Consumer Gate today. */
export function ConnectorPlanned() {
  return (
    <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs">
      <Planned
        label="Connector"
        section="connector"
        tooltip="The Connector at a Consumer's edge will tell it of Ontology changes that affect its Tasks and enforce its Consumer Gate before it takes a version; today the pipeline's CI enforces it."
      >
        Connector: not connected
      </Planned>
    </div>
  )
}

/** The planned AI drafting of Consumers' Tasks and Competency Questions, as a disabled action. */
export function DraftWithAiPlanned() {
  return (
    <Planned
      label="Draft Tasks & questions with AI"
      section="ai-and-mcp-authoring"
      tooltip="An agent will propose Tasks and Competency Questions; a person accepts them as a new Use Case Version."
    >
      <Button size="sm" variant="outline" disabled>
        <Sparkles />
        Draft Tasks & questions with AI
      </Button>
    </Planned>
  )
}
