import { useCallback, useId, useMemo, type ReactNode } from 'react'
import { useQueries, useQuery } from '@tanstack/react-query'
import { Link, useSearchParams } from 'react-router'
import { isNotFound } from '@/api/client'
import { type GatePreview, gatePreviewsQuery } from '@/api/gate-previews'
import { type GateResult, gateResultsQuery } from '@/api/gate-results'
import type { EvaluationResult } from '@/api/ontology-versions'
import { type ConstructionRun, runEvaluationsQuery, runQuery } from '@/api/runs'
import { kgUrl } from '@/app/knowledge-graph-sections'
import { ErrorAlert } from '@/components/ErrorAlert'
import { PageHeader } from '@/components/PageHeader'
import { RunStatusLabel } from '@/components/RunStatusLabel'
import { Label } from '@/components/ui/label'
import { Skeleton } from '@/components/ui/skeleton'
import { Switch } from '@/components/ui/switch'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { formatDateTime, formatMetric } from '@/lib/format'
import { setOrDeleteParam } from '@/lib/search-params'
import { NotFoundPage } from '@/pages/NotFoundPage'
import { useComparedIds, useKnowledgeGraphName } from '../params'
import {
  type ComparedValue,
  type ComparisonRow,
  type Kpi,
  type KpiSummary,
  compareRuns,
  differs,
  gateRows,
  kpiSummary,
  kpiVerdict,
  runGating,
} from './compare'
import { GatePreviewNote, KpiSummaryBar, NeverGatedHint, NoResult, PassFail, VerdictBadge } from './gate-verdicts'
import { shortRunId } from './runs'

const linkClass = 'text-primary underline-offset-4 hover:underline'
const none = <span className="text-muted-foreground">—</span>

/**
 * `/kg/:name/runs/compare?id=<run id>&id=<run id>…`: the runs side by side (their status,
 * Declared Ontology, Candidate, Conformance, params, metrics and Evaluator results),
 * composed from the run and run evaluation routes as `Client.compare_runs` does.
 * `&diff=only` ("Show diff only") hides the rows whose values are identical.
 */
export function RunComparePage() {
  const name = useKnowledgeGraphName()
  const [searchParams, setSearchParams] = useSearchParams()
  const ids = useComparedIds()
  const diffOnly = searchParams.get('diff') === 'only'
  const setDiffOnly = useCallback(
    (on: boolean) =>
      setSearchParams(
        (p) => setOrDeleteParam(p, 'diff', on ? 'only' : null),
        { replace: true },
      ),
    [setSearchParams],
  )

  const runs = useQueries({
    queries: ids.map(runQuery),
    combine: (queries) => queries,
  })
  const evaluations = useQueries({
    queries: ids.map((id) => runEvaluationsQuery(name, id)),
    combine: (queries) => queries,
  })
  const gateResults = useQuery(gateResultsQuery(name))
  const gatePreviews = useQuery(gatePreviewsQuery(name))

  const header = (
    <PageHeader
      title={`Compare ${ids.length} Construction Runs`}
      actions={
        <div className="flex items-center gap-2">
          <Switch id="diff-only" checked={diffOnly} onCheckedChange={setDiffOnly} />
          <Label htmlFor="diff-only">Show diff only</Label>
        </div>
      }
    />
  )

  // A run of another Knowledge Graph is not found here, as an unknown or unreadable one is.
  const missing = ids.find(
    (_id, i) =>
      (runs[i].isError && isNotFound(runs[i].error)) || (runs[i].data && runs[i].data.knowledge_graph !== name),
  )
  if (missing !== undefined) {
    return (
      <NotFoundPage
        title="Construction Run not found"
        message={`Knowledge Graph “${name}” has no Construction Run ${missing}.`}
      />
    )
  }
  if (ids.length < 2) {
    return (
      <>
        {header}
        <p className="text-sm">
          Select two or more runs to compare.{' '}
          <Link to={kgUrl(name, 'runs')} className={linkClass}>
            Back to Construction Runs
          </Link>
        </p>
      </>
    )
  }
  const failed = [...runs, ...evaluations, gateResults, gatePreviews].find((q) => q.isError)
  if (failed) {
    return (
      <>
        {header}
        <ErrorAlert error={failed.error} />
      </>
    )
  }
  const loadedRuns = runs.map((q) => q.data)
  const loadedEvaluations = evaluations.map((q) => q.data)
  if (
    loadedRuns.some((r) => r === undefined) ||
    loadedEvaluations.some((e) => e === undefined) ||
    gateResults.data === undefined ||
    gatePreviews.data === undefined
  ) {
    return (
      <>
        {header}
        <Skeleton className="h-48 w-full" />
      </>
    )
  }
  return (
    <>
      {header}
      <Comparison
        runs={loadedRuns as ConstructionRun[]}
        evaluations={loadedEvaluations as EvaluationResult[][]}
        gateResults={gateResults.data}
        gatePreviews={gatePreviews.data}
        diffOnly={diffOnly}
      />
    </>
  )
}

/**
 * One compared row: what it is, the runs' values (to tell if they differ), how to show
 * one, and for a gated KPI how the runs fare on it.
 */
interface Row {
  label: string
  values: readonly ComparedValue[]
  render: (i: number) => ReactNode
  summary?: KpiSummary | null
}

function Comparison({
  runs,
  evaluations,
  gateResults,
  gatePreviews,
  diffOnly,
}: {
  runs: ConstructionRun[]
  evaluations: EvaluationResult[][]
  gateResults: GateResult[]
  gatePreviews: GatePreview[]
  diffOnly: boolean
}) {
  const comparison = useMemo(() => compareRuns(runs, evaluations), [runs, evaluations])
  const gatings = useMemo(
    () => runs.map((run) => runGating(run.id, gateResults, gatePreviews)),
    [runs, gateResults, gatePreviews],
  )
  const metric = (value: number | null) =>
    value === null ? none : <span className="tabular-nums">{formatMetric(value)}</span>
  const keyed = <V extends ComparedValue>(rows: ComparisonRow<V>[], show: (value: V) => ReactNode): Row[] =>
    rows.map((row) => ({ label: row.key, values: row.values, render: (i) => show(row.values[i]) }))
  /** A KPI row: each value with its verdict, and the KPI's summary when it is gated. */
  const kpiRow = (label: string, kpi: Kpi, values: (number | null)[]): Row => {
    const verdicts = values.map((value, i) => kpiVerdict(kpi, value, gatings[i]))
    return {
      label,
      values,
      summary: kpiSummary(verdicts),
      render: (i) => (
        <span className="inline-flex flex-wrap items-center gap-x-2">
          {verdicts[i].verdict === 'no-result' ? <NoResult /> : metric(values[i])}
          <VerdictBadge verdict={verdicts[i]} />
        </span>
      ),
    }
  }
  const gates = gateRows(gatings)
  const gateCells = gates.gates.map(
    (gate): Row => ({
      label: gate.name,
      values: gate.cells.map((c) => (c === null ? null : String(c.passed))),
      render: (i) => {
        const cell = gate.cells[i]
        return cell === null ? none : <PassFail passed={cell.passed} origin={cell.origin} />
      },
    }),
  )
  const allPassed: Row = {
    label: 'All Gates passed',
    values: [],
    render: (i) => {
      const cell = gates.overall[i]
      return cell === null ? none : <PassFail passed={cell.passed} origin={cell.origin} />
    },
  }
  const source = gatePreviews[0]?.source
  const neverGated = gatePreviews.length === 0 && gateResults.length === 0

  const version = (number: number | null) =>
    number === null ? (
      none
    ) : (
      <Link to={kgUrl(runs[0].knowledge_graph, 'versions', number)} className={linkClass}>
        v{number}
      </Link>
    )
  const overview: Row[] = [
    { label: 'Status', values: runs.map((r) => r.status), render: (i) => <RunStatusLabel status={runs[i].status} /> },
    {
      label: 'Started',
      values: runs.map((r) => r.started_at),
      render: (i) => <time dateTime={runs[i].started_at}>{formatDateTime(runs[i].started_at)}</time>,
    },
    {
      label: 'Declared Ontology',
      values: comparison.declaredOntology,
      render: (i) => version(comparison.declaredOntology[i]),
    },
    { label: 'Candidate', values: comparison.candidate, render: (i) => version(comparison.candidate[i]) },
    kpiRow('Conformance', { kind: 'conformance' }, comparison.conformance),
  ]

  return (
    <div className="space-y-6">
      {neverGated ? (
        <NeverGatedHint />
      ) : (
        source !== undefined && <GatePreviewNote knowledgeGraph={runs[0].knowledge_graph} source={source} />
      )}
      <ComparisonTable label="Runs" runs={runs} rows={overview} diffOnly={diffOnly} />
      <ComparisonTable
        label="Params"
        runs={runs}
        rows={keyed(comparison.params, (v) => v ?? none)}
        diffOnly={diffOnly}
        empty="No params logged."
      />
      <ComparisonTable
        label="Metrics"
        runs={runs}
        rows={keyed(comparison.metrics, metric)}
        diffOnly={diffOnly}
        empty="No metrics logged."
      />
      <ComparisonTable
        label="Evaluator results"
        runs={runs}
        rows={comparison.evaluations.map((row) => kpiRow(row.key, { kind: 'evaluator', key: row.key }, row.values))}
        diffOnly={diffOnly}
        empty="No Evaluator results."
      />
      {gateCells.length > 0 && (
        <ComparisonTable
          label="Gates"
          runs={runs}
          rows={gateCells}
          pinned={allPassed}
          diffOnly={diffOnly}
        />
      )}
    </div>
  )
}

function ComparisonTable({
  label,
  runs,
  rows,
  pinned,
  diffOnly,
  empty,
}: {
  label: string
  runs: ConstructionRun[]
  rows: Row[]
  /** A last row that "Show diff only" never hides. */
  pinned?: Row
  diffOnly: boolean
  /** Shown when no run has any row. */
  empty?: string
}) {
  const headingId = useId()
  const shown = [...(diffOnly ? rows.filter((row) => differs(row.values)) : rows), ...(pinned ? [pinned] : [])]
  const message =
    rows.length === 0 ? (empty ?? null) : shown.length === 0 ? 'No differences.' : null
  return (
    <section aria-labelledby={headingId} className="space-y-2">
      <h2 id={headingId} className="text-sm font-semibold">
        {label}
      </h2>
      <Table aria-label={label}>
        <TableHeader>
          <TableRow>
            <TableHead className="w-56">
              <span className="sr-only">{label === 'Runs' ? 'Field' : 'Key'}</span>
            </TableHead>
            {runs.map((run) => (
              <TableHead key={run.id}>
                <Link to={kgUrl(run.knowledge_graph, 'runs', run.id)} title={run.id} className={`font-mono ${linkClass}`}>
                  {shortRunId(run.id)}
                </Link>
              </TableHead>
            ))}
          </TableRow>
        </TableHeader>
        <TableBody>
          {message !== null ? (
            <TableRow>
              <TableCell colSpan={runs.length + 1} className="text-muted-foreground">
                {message}
              </TableCell>
            </TableRow>
          ) : (
            shown.map((row) => (
              <TableRow key={row.label}>
                <TableHead scope="row" className="font-medium">
                  {row.label}
                  {row.summary && <KpiSummaryBar summary={row.summary} />}
                </TableHead>
                {runs.map((run, i) => (
                  <TableCell key={run.id}>{row.render(i)}</TableCell>
                ))}
              </TableRow>
            ))
          )}
        </TableBody>
      </Table>
    </section>
  )
}
