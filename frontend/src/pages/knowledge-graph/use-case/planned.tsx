import { Sparkles } from 'lucide-react'
import { Planned } from '@/components/Planned'
import { Button } from '@/components/ui/button'

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
