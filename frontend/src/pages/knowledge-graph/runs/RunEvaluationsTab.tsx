import { CircleCheck, CircleX, TriangleAlert } from 'lucide-react'
import type { EvaluationResult } from '@/api/ontology-versions'
import { useRunEvaluations } from '@/api/runs'
import { ErrorAlert } from '@/components/ErrorAlert'
import { Skeleton } from '@/components/ui/skeleton'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { EvaluatorResultTable, Panel } from '../versions/OverviewTab'
import { useConstructionRunTab } from './run-context'

/** `evaluation.run.CQ_EXECUTION_EVALUATOR`: executes the Use Case's Competency Questions. */
const CQ_EXECUTION_EVALUATOR = 'competency_question_execution'

/**
 * One executed Competency Question, from a Detail of the execution Evaluator. Only
 * these fields are read: the verdict, which check judged it and an exception type.
 * Rows are never stored (ADR 0001), and the UI shows nothing else from the Detail.
 */
interface ExecutedQuestion {
  id: string
  status: 'passed' | 'failed' | 'error'
  check: 'non_empty' | 'expected_answer'
  error: string | null
}

function executedQuestions(result: EvaluationResult): ExecutedQuestion[] {
  return result.details.map((detail) => {
    const data = detail.data ?? {}
    return {
      id: detail.item,
      status: data.status as ExecutedQuestion['status'],
      check: data.check as ExecutedQuestion['check'],
      error: typeof data.error === 'string' ? data.error : null,
    }
  })
}

const STATUS = {
  passed: { label: 'Passed', Icon: CircleCheck, className: 'text-emerald-600 dark:text-emerald-500' },
  failed: { label: 'Failed', Icon: CircleX, className: 'text-destructive' },
  error: { label: 'Error', Icon: TriangleAlert, className: 'text-destructive' },
} as const

const CHECK = { non_empty: 'non-empty result', expected_answer: 'expected answer' } as const

/** The run page's Evaluations tab: every run Evaluator's metrics, then each executed Competency Question. */
export function RunEvaluationsTab() {
  const run = useConstructionRunTab()
  const results = useRunEvaluations(run.knowledge_graph, run.id)
  if (results.isPending) return <Skeleton className="h-32 w-full" />
  if (results.isError) return <ErrorAlert error={results.error} />
  const execution = results.data.find((r) => r.evaluator === CQ_EXECUTION_EVALUATOR)
  return (
    <div className="space-y-8">
      <Panel title="Evaluator results">
        <EvaluatorResultTable results={results.data} empty="No Evaluator results for this run." />
      </Panel>
      {execution && (
        <Panel title="Competency Questions">
          <ExecutedQuestions result={execution} />
        </Panel>
      )}
    </div>
  )
}

function ExecutedQuestions({ result }: { result: EvaluationResult }) {
  const questions = executedQuestions(result)
  return (
    <div className="space-y-2">
      <p className="text-sm text-muted-foreground">
        Each Competency Question with a query, executed read-only against the graph
        {result.use_case_version !== null && ` (Use Case Version ${result.use_case_version})`}. Only
        the verdict is kept, never the rows.
      </p>
      {questions.length === 0 ? (
        <p className="text-sm text-muted-foreground">No Competency Question has a query.</p>
      ) : (
        <Table aria-label="Competency Questions">
          <TableHeader>
            <TableRow>
              <TableHead>Competency Question</TableHead>
              <TableHead>Result</TableHead>
              <TableHead>Check</TableHead>
              <TableHead>Error type</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {questions.map((q) => {
              const { label, Icon, className } = STATUS[q.status] ?? STATUS.error
              return (
                <TableRow key={q.id}>
                  <TableCell className="font-mono text-xs">{q.id}</TableCell>
                  <TableCell>
                    <span className="inline-flex items-center gap-1.5">
                      <Icon aria-hidden className={`size-4 ${className}`} />
                      {label}
                    </span>
                  </TableCell>
                  <TableCell>{CHECK[q.check] ?? q.check}</TableCell>
                  <TableCell className="font-mono text-xs">
                    {q.error ?? <span className="text-muted-foreground">—</span>}
                  </TableCell>
                </TableRow>
              )
            })}
          </TableBody>
        </Table>
      )}
    </div>
  )
}
