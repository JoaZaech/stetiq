import { Sparkles } from 'lucide-react'
import { Planned } from '@/components/Planned'
import { Button } from '@/components/ui/button'

/** A Consumer card's planned edge: its Connector and its Consumer Gate (docs/vision.md). */
export function ConsumerEdgePlanned() {
  return (
    <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs">
      <Planned
        label="Connector"
        section="connector"
        tooltip="The Connector at a Consumer's edge tells it of Ontology changes that affect its Tasks and enforces its Consumer Gate."
      >
        Connector: not connected
      </Planned>
      <Planned
        label="Consumer Gate"
        section="consumer-gate"
        tooltip="A rule, for this Consumer, that must hold for it to take an Ontology Version."
      >
        Consumer Gate: none
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
