import { useCallback, useId, useMemo, type ReactNode } from 'react'
import { Link, useSearchParams } from 'react-router'
import type { EvaluationResult } from '@/api/ontology-versions'
import { useRunEvaluations } from '@/api/runs'
import { useUseCaseVersions } from '@/api/use-cases'
import { kgUrl } from '@/app/knowledge-graph-sections'
import { ErrorAlert } from '@/components/ErrorAlert'
import { InfoTip } from '@/components/InfoTip'
import { StatusLabel, type StatusTone } from '@/components/StatusLabel'
import { Skeleton } from '@/components/ui/skeleton'
import { useSheetParam } from '@/lib/sheet-param'
import { helpUrl } from '@/pages/help/guide-index'
import { FindingsTable } from '../evaluation/FindingsTable'
import { findingsFromMismatches } from '../evaluation/findings'
import { EvaluatorResults } from '../versions/EvaluatorResults'
import { CompetencyQuestionSheet } from '../use-case/CompetencyQuestionSheet'
import { SheetSection } from '../use-case/sheet-section'
import { FINDING_PARAM, useConstructionRunTab } from './run-context'
import { CQ_EXECUTION_EVALUATOR, type ExecutedQuestion, executedQuestions } from './runs'

const GUIDE = `${helpUrl('using-the-web-ui')}#construction-runs`

const STATUS: Record<ExecutedQuestion['status'], { label: string; tone: StatusTone }> = {
  passed: { label: 'Passed', tone: 'success' },
  failed: { label: 'Failed', tone: 'failure' },
  error: { label: 'Error', tone: 'error' },
}

const CHECK = { non_empty: 'non-empty result', expected_answer: 'expected answer' } as const

const SHEET_KINDS = ['question'] as const

/**
 * The run page's Evaluation tab, laid out as every evaluation is: the Conformance
 * findings in the shared findings table (opened filtered by `?finding=`), the Evaluator
 * cards with every metric folded away, then each executed Competency Question.
 */
export function RunEvaluationTab() {
  const run = useConstructionRunTab()
  const [params] = useSearchParams()
  const finding = params.get(FINDING_PARAM) ?? ''
  const rows = useMemo(() => findingsFromMismatches(run.conformance?.mismatches ?? []), [run.conformance])
  return (
    <div className="space-y-8">
      <Section
        title="Findings"
        tip="Conformance mismatches: what the run observed against what its Declared Ontology declares. A deprecated value is reported but conforms."
      >
        {run.conformance === null ? (
          <p className="text-sm text-muted-foreground">No Conformance: the run ended without an Observation.</p>
        ) : (
          <>
            {run.candidate_version !== null && (
              <p className="text-xs text-muted-foreground" role="note" aria-label="Judged against">
                Judged against Candidate{' '}
                <Link
                  to={kgUrl(run.knowledge_graph, 'versions', run.candidate_version)}
                  className="text-primary underline-offset-4 hover:underline"
                >
                  v{run.candidate_version}
                </Link>
              </p>
            )}
            <FindingsTable key={finding} rows={rows} initialFinding={finding} empty="No mismatches." />
          </>
        )}
      </Section>
      <RunEvaluatorResults />
    </div>
  )
}

/** A titled part of the tab, its explanation in an ⓘ beside the title. */
function Section({ title, tip, children }: { title: string; tip?: string; children: ReactNode }) {
  const id = useId()
  return (
    <section aria-labelledby={id} className="min-w-0 space-y-3">
      <h2 className="flex items-center gap-1.5 text-sm font-semibold">
        <span id={id}>{title}</span>
        {tip && (
          <InfoTip label={title} to={GUIDE}>
            {tip}
          </InfoTip>
        )}
      </h2>
      {children}
    </section>
  )
}

function RunEvaluatorResults() {
  const run = useConstructionRunTab()
  const results = useRunEvaluations(run.knowledge_graph, run.id)
  if (results.isPending) return <Skeleton className="h-32 w-full" />
  if (results.isError) return <ErrorAlert error={results.error} />
  const execution = results.data.find((r) => r.evaluator === CQ_EXECUTION_EVALUATOR)
  return (
    <>
      <Section title="Evaluator results">
        <EvaluatorResults results={results.data} empty="No Evaluator results for this run." />
      </Section>
      {execution && (
        <Section
          title="Competency Questions"
          tip="Each Competency Question with a query, executed read-only against the graph. Only the verdict is kept, never the rows."
        >
          <ExecutedQuestions knowledgeGraph={run.knowledge_graph} result={execution} />
        </Section>
      )}
    </>
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
      {result.use_case_version !== null && (
        <p className="text-xs text-muted-foreground">Use Case Version {result.use_case_version}</p>
      )}
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
