import { useCallback } from 'react'
import type { EvaluationResult } from '@/api/ontology-versions'
import { useRunEvaluations } from '@/api/runs'
import { useUseCaseVersions } from '@/api/use-cases'
import { ErrorAlert } from '@/components/ErrorAlert'
import { StatusLabel, type StatusTone } from '@/components/StatusLabel'
import { Skeleton } from '@/components/ui/skeleton'
import { useSheetParam } from '@/lib/sheet-param'
import { EvaluatorResults } from '../versions/EvaluatorResults'
import { Panel } from '../versions/OverviewTab'
import { CompetencyQuestionSheet } from '../use-case/CompetencyQuestionSheet'
import { SheetSection } from '../use-case/sheet-section'
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

const STATUS: Record<ExecutedQuestion['status'], { label: string; tone: StatusTone }> = {
  passed: { label: 'Passed', tone: 'success' },
  failed: { label: 'Failed', tone: 'failure' },
  error: { label: 'Error', tone: 'error' },
}

const CHECK = { non_empty: 'non-empty result', expected_answer: 'expected answer' } as const

const SHEET_KINDS = ['question'] as const

/**
 * The run page's Evaluations tab: one card per run Evaluator with every metric behind
 * "Show all metrics", then each executed Competency Question.
 */
export function RunEvaluationsTab() {
  const run = useConstructionRunTab()
  const results = useRunEvaluations(run.knowledge_graph, run.id)
  if (results.isPending) return <Skeleton className="h-32 w-full" />
  if (results.isError) return <ErrorAlert error={results.error} />
  const execution = results.data.find((r) => r.evaluator === CQ_EXECUTION_EVALUATOR)
  return (
    <div className="space-y-8">
      <Panel title="Evaluator results">
        <EvaluatorResults results={results.data} empty="No Evaluator results for this run." />
      </Panel>
      {execution && (
        <Panel title="Competency Questions">
          <ExecutedQuestions knowledgeGraph={run.knowledge_graph} result={execution} />
        </Panel>
      )}
    </div>
  )
}

/**
 * The executed questions as the Use Case page lists them: question text and this run's
 * result. A row opens the question's sheet (`?sheet=question:<id>`), with this run's
 * result, check and error type added.
 */
function ExecutedQuestions({ knowledgeGraph, result }: { knowledgeGraph: string; result: EvaluationResult }) {
  const questions = executedQuestions(result)
  const versions = useUseCaseVersions(knowledgeGraph)
  const { sheet, openSheet, closeSheet } = useSheetParam(SHEET_KINDS)
  const open = useCallback((id: string) => openSheet({ kind: 'question', id }), [openSheet])
  if (versions.isError) return <ErrorAlert error={versions.error} />
  if (versions.isPending) return <Skeleton className="h-20 w-full" />
  // The questions as they were in the Use Case Version the run executed.
  const version = versions.data.find((v) => v.number === result.use_case_version)
  const question = (id: string) => version?.use_case.competency_questions.find((q) => q.id === id)
  const selected = sheet && questions.find((q) => q.id === sheet.id)
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
        <ul aria-label="Competency Questions" className="divide-y overflow-hidden rounded-lg border">
          {questions.map((q) => (
            <li key={q.id}>
              <button
                type="button"
                onClick={() => open(q.id)}
                className="flex w-full flex-wrap items-center gap-x-3 gap-y-1 px-3 py-2 text-left text-sm hover:bg-muted/50 focus-visible:bg-muted/50 focus-visible:outline-none"
              >
                <span className="min-w-0 flex-1">{question(q.id)?.question ?? q.id}</span>
                <StatusLabel {...(STATUS[q.status] ?? STATUS.error)} />
              </button>
            </li>
          ))}
        </ul>
      )}
      {version && (
        <CompetencyQuestionSheet
          knowledgeGraph={knowledgeGraph}
          useCaseVersion={version}
          question={selected ? question(selected.id) : undefined}
          onClose={closeSheet}
        >
          {selected && <InThisRun question={selected} />}
        </CompetencyQuestionSheet>
      )}
    </div>
  )
}

/** The run's verdict on a question, in its sheet: the result, which check judged it and any error type. */
function InThisRun({ question }: { question: ExecutedQuestion }) {
  return (
    <SheetSection title="In this run">
      <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-2">
        <dt className="text-muted-foreground">Result</dt>
        <dd>
          <StatusLabel {...(STATUS[question.status] ?? STATUS.error)} />
        </dd>
        <dt className="text-muted-foreground">Check</dt>
        <dd>{CHECK[question.check] ?? question.check}</dd>
        <dt className="text-muted-foreground">Error type</dt>
        <dd>
          {question.error === null ? (
            <span className="text-muted-foreground">—</span>
          ) : (
            <code className="font-mono text-xs">{question.error}</code>
          )}
        </dd>
      </dl>
    </SheetSection>
  )
}
