import type { CompetencyQuestionField } from './compare'

const None = () => <span className="text-muted-foreground">—</span>

/** A Cypher query, monospace and as written. */
export function Query({ value }: { value: string | undefined }) {
  if (value === undefined) return <None />
  return <pre className="font-mono text-xs whitespace-pre-wrap">{value}</pre>
}

/** An expected answer: any JSON value, pretty-printed. */
export function ExpectedAnswer({ value }: { value: unknown }) {
  if (value === undefined || value === null) return <None />
  return <pre className="font-mono text-xs whitespace-pre-wrap">{JSON.stringify(value, null, 2)}</pre>
}

/** A Concept mapping: one Concept reference per line. */
export function ConceptMapping({ value }: { value: string[] | undefined }) {
  if (!value || value.length === 0) return <None />
  return (
    <ul className="space-y-0.5">
      {value.map((ref) => (
        <li key={ref}>
          <code className="font-mono text-xs">{ref}</code>
        </li>
      ))}
    </ul>
  )
}

/** Any one field's value, as its column shows it. */
export function FieldValue({ field, value }: { field: CompetencyQuestionField; value: unknown }) {
  switch (field) {
    case 'question':
      return typeof value === 'string' ? <span>{value}</span> : <None />
    case 'query':
      return <Query value={typeof value === 'string' ? value : undefined} />
    case 'expected_answer':
      return <ExpectedAnswer value={value} />
    case 'concepts':
      return <ConceptMapping value={Array.isArray(value) ? (value as string[]) : undefined} />
  }
}
