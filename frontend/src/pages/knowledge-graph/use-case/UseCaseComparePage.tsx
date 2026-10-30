import { useId, type ReactNode } from 'react'
import { useUseCaseVersions, type CompetencyQuestion, type UseCaseVersion } from '@/api/use-cases'
import { ErrorAlert } from '@/components/ErrorAlert'
import { PageHeader } from '@/components/PageHeader'
import { Skeleton } from '@/components/ui/skeleton'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { NotFoundPage } from '@/pages/NotFoundPage'
import { parseVersionNumber } from '@/lib/version-number'
import { useComparedIds, useKnowledgeGraphName } from '../params'
import { compareUseCases, FIELD_LABELS, type ChangedQuestion } from './compare'
import { ConceptMapping, ExpectedAnswer, FieldValue, Query } from './fields'

/** `/kg/:name/use-case/compare?id=N&id=M`: what changed from Use Case Version N to M. */
export function UseCaseComparePage() {
  const name = useKnowledgeGraphName()
  const ids = useComparedIds()
  const versions = useUseCaseVersions(name)
  const [fromParam = '', toParam = ''] = ids.length === 2 ? ids : []

  if (versions.isError) return <ErrorAlert error={versions.error} />
  if (versions.isPending) return <Skeleton className="h-32 w-full" />
  const from = findVersion(versions.data, fromParam)
  const to = findVersion(versions.data, toParam)
  if (!from || !to) {
    const missing = from ? toParam : fromParam
    return (
      <NotFoundPage
        title="Use Case Version not found"
        message={`Knowledge Graph “${name}” has no Use Case Version ${missing}.`}
      />
    )
  }
  return (
    <>
      <PageHeader
        title={`Compare v${from.number} → v${to.number}`}
        description="Competency Questions are matched by id."
      />
      <Comparison from={from} to={to} />
    </>
  )
}

function findVersion(versions: UseCaseVersion[], raw: string): UseCaseVersion | undefined {
  const number = parseVersionNumber(raw)
  return versions.find((v) => v.number === number)
}

function Comparison({ from, to }: { from: UseCaseVersion; to: UseCaseVersion }) {
  const { description, added, changed, removed } = compareUseCases(from.use_case, to.use_case)
  if (!description && added.length + changed.length + removed.length === 0) {
    return (
      <p className="text-sm text-muted-foreground">
        These Use Case Versions ask the same Competency Questions.
      </p>
    )
  }
  return (
    <div className="space-y-8">
      {description && (
        <Panel title="Description">
          <ValueTable
            label="Description"
            rows={[{ label: 'Description', before: description.before, after: description.after }]}
          />
        </Panel>
      )}
      <Panel title="Added" count={added.length}>
        <QuestionList questions={added} empty="No Competency Questions added." />
      </Panel>
      <Panel title="Changed" count={changed.length}>
        {changed.length === 0 ? (
          <p className="text-sm text-muted-foreground">No Competency Questions changed.</p>
        ) : (
          changed.map((question) => <ChangedQuestionTable key={question.id} question={question} />)
        )}
      </Panel>
      <Panel title="Removed" count={removed.length}>
        <QuestionList questions={removed} empty="No Competency Questions removed." />
      </Panel>
    </div>
  )
}

function Panel({ title, count, children }: { title: string; count?: number; children: ReactNode }) {
  const id = useId()
  return (
    <section aria-labelledby={id} className="min-w-0 space-y-3">
      <h2 id={id} className="text-sm font-semibold">
        {title}
        {count !== undefined && <span className="ml-1.5 text-muted-foreground">{count}</span>}
      </h2>
      {children}
    </section>
  )
}

/** Added or removed questions, every field shown. */
function QuestionList({ questions, empty }: { questions: CompetencyQuestion[]; empty: string }) {
  if (questions.length === 0) return <p className="text-sm text-muted-foreground">{empty}</p>
  return (
    <ul className="divide-y rounded-lg border">
      {questions.map((q) => (
        <li key={q.id} className="grid gap-2 p-3 text-sm">
          <div className="flex flex-wrap items-baseline gap-2">
            <code className="font-mono text-xs">{q.id}</code>
            <span>{q.question}</span>
          </div>
          <dl className="grid grid-cols-[auto_minmax(0,1fr)] gap-x-6 gap-y-1">
            <dt className="text-muted-foreground">{FIELD_LABELS.query}</dt>
            <dd className="min-w-0">
              <Query value={q.query} />
            </dd>
            <dt className="text-muted-foreground">{FIELD_LABELS.expected_answer}</dt>
            <dd className="min-w-0">
              <ExpectedAnswer value={q.expected_answer} />
            </dd>
            <dt className="text-muted-foreground">{FIELD_LABELS.concepts}</dt>
            <dd className="min-w-0">
              <ConceptMapping value={q.concepts} />
            </dd>
          </dl>
        </li>
      ))}
    </ul>
  )
}

/** One changed question: a row per changed field, before and after. */
function ChangedQuestionTable({ question }: { question: ChangedQuestion }) {
  return (
    <div className="space-y-1">
      <code className="font-mono text-xs">{question.id}</code>
      <ValueTable
        label={question.id}
        rows={question.fields.map(({ field, before, after }) => ({
          label: FIELD_LABELS[field],
          before: <FieldValue field={field} value={before} />,
          after: <FieldValue field={field} value={after} />,
        }))}
      />
    </div>
  )
}

function ValueTable({
  label,
  rows,
}: {
  label: string
  rows: { label: string; before: ReactNode; after: ReactNode }[]
}) {
  return (
    <Table aria-label={label}>
      <TableHeader>
        <TableRow>
          <TableHead className="w-40">Field</TableHead>
          <TableHead>Before</TableHead>
          <TableHead>After</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {rows.map((row) => (
          <TableRow key={row.label}>
            <TableCell className="align-top text-muted-foreground">{row.label}</TableCell>
            <TableCell className="align-top whitespace-normal">{row.before ?? '—'}</TableCell>
            <TableCell className="align-top whitespace-normal">{row.after ?? '—'}</TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  )
}
