const SNIPPET = `from pathlib import Path

import stetiq

client = stetiq.Client()  # or stetiq.Client("http://<server>") with $STETIQ_TOKEN
client.create_knowledge_graph("support", ontology=Path("ontology.yaml"))`

interface NoKnowledgeGraphsProps {
  /** The level of its "No Knowledge Graphs yet" heading on the page it sits in. */
  headingLevel?: 2 | 3
}

/** No Knowledge Graph at all: show how to register the first Ontology Version. */
export function NoKnowledgeGraphs({ headingLevel = 2 }: NoKnowledgeGraphsProps) {
  const Heading = headingLevel === 3 ? 'h3' : 'h2'
  return (
    <div className="rounded-lg border border-dashed p-8">
      <Heading className="text-base font-semibold">No Knowledge Graphs yet</Heading>
      <p className="mt-1 max-w-prose text-sm text-muted-foreground">
        Create one from the Python SDK. Its Declared Ontology becomes Ontology Version 1 and the
        Contract Alias <code className="font-mono">production</code> points to it.
      </p>
      <pre className="mt-4 overflow-x-auto rounded-md bg-muted p-4 text-sm">
        <code className="font-mono">{SNIPPET}</code>
      </pre>
    </div>
  )
}
