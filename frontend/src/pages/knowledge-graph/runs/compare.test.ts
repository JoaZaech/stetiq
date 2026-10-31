import { describe, expect, it } from 'vitest'
import type { GatePreview } from '@/api/gate-previews'
import type { GateResult } from '@/api/gate-results'
import type { EvaluationResult } from '@/api/ontology-versions'
import type { ConstructionRun } from '@/api/runs'
import { compareRuns, differs, gateRows, kpiSummary, kpiVerdict, runChartPoints } from './compare'

function run(overrides: Partial<ConstructionRun>): ConstructionRun {
  return {
    id: 'r',
    knowledge_graph: 'support',
    ontology_version: 1,
    status: 'finished',
    started_at: '2026-10-30T11:00:00Z',
    ended_at: '2026-10-30T11:01:00Z',
    params: {},
    metrics: {},
    observation_id: 'o',
    conformance: null,
    candidate_version: null,
    ...overrides,
  }
}

function evaluation(
  evaluator: string,
  metrics: Record<string, number>,
  overrides: Partial<EvaluationResult> = {},
): EvaluationResult {
  return {
    knowledge_graph: 'support',
    subject_kind: 'construction_run',
    subject_id: 'r',
    evaluator,
    metrics,
    details: [],
    created_at: '2026-10-30T11:01:00Z',
    parameters: {},
    use_case_version: null,
    ...overrides,
  }
}

describe('compareRuns', () => {
  const a = run({
    id: 'a',
    params: { extractor: 'llm', temperature: '0.2' },
    metrics: { recall: 0.8, precision: 0.91 },
    conformance: { score: 0.5, mismatches: [] },
  })
  const b = run({
    id: 'b',
    ontology_version: 2,
    params: { extractor: 'llm', batch: '10' },
    metrics: { recall: 0.8 },
  })

  it('puts each param and metric key on one row, sorted, with a value per run (null where not logged)', () => {
    const comparison = compareRuns([a, b], [[], []])
    expect(comparison.params).toEqual([
      { key: 'batch', values: [null, '10'] },
      { key: 'extractor', values: ['llm', 'llm'] },
      { key: 'temperature', values: ['0.2', null] },
    ])
    expect(comparison.metrics).toEqual([
      { key: 'precision', values: [0.91, null] },
      { key: 'recall', values: [0.8, 0.8] },
    ])
  })

  it('compares the Declared Ontology, Candidate and Conformance score of each run', () => {
    const comparison = compareRuns([a, b], [[], []])
    expect(comparison.declaredOntology).toEqual([1, 2])
    expect(comparison.candidate).toEqual([null, null])
    expect(comparison.conformance).toEqual([0.5, null])
  })

  it('keys Evaluator metrics `<evaluator>/<metric>`, as the version table does', () => {
    const comparison = compareRuns(
      [a, b],
      [[evaluation('conformance', { score: 0.5 })], [evaluation('conformance', { score: 0.7 }), evaluation('observed_schema', { node_types: 2 })]],
    )
    expect(comparison.evaluations).toEqual([
      { key: 'conformance/score', values: [0.5, 0.7] },
      { key: 'observed_schema/node_types', values: [null, 2] },
    ])
  })
})

describe('differs', () => {
  it('is false when every run has the same value, missing ones included', () => {
    expect(differs(['llm', 'llm', 'llm'])).toBe(false)
    expect(differs([null, null])).toBe(false)
  })

  it('is true when any value differs, or one run lacks it', () => {
    expect(differs([0.8, 0.9])).toBe(true)
    expect(differs(['llm', null])).toBe(true)
  })
})

describe('runChartPoints', () => {
  it('plots each run at its start time with its metrics and Conformance score', () => {
    const points = runChartPoints([
      run({ started_at: '2026-10-30T11:00:00Z', metrics: { recall: 0.8 }, conformance: { score: 0.5, mismatches: [] } }),
      run({ started_at: '2026-10-30T12:00:00Z', metrics: { recall: 0.9 } }),
    ])
    expect(points).toEqual([
      { x: Date.parse('2026-10-30T11:00:00Z'), metrics: { recall: 0.8, Conformance: 0.5 } },
      { x: Date.parse('2026-10-30T12:00:00Z'), metrics: { recall: 0.9 } },
    ])
  })

  it("adds each run's Evaluator results, keyed `<evaluator>/<metric>`, from the Knowledge Graph-wide list", () => {
    const points = runChartPoints(
      [
        run({ id: 'a', started_at: '2026-10-30T11:00:00Z', metrics: { recall: 0.8 } }),
        run({ id: 'b', started_at: '2026-10-30T12:00:00Z' }),
      ],
      [
        evaluation('observed_schema', { node_types: 2 }, { subject_id: 'b' }),
        evaluation('conformance', { score: 0.5 }, { subject_id: 'a' }),
        evaluation('observed_schema', { node_types: 3 }, { subject_id: 'a' }),
      ],
    )
    expect(points).toEqual([
      {
        x: Date.parse('2026-10-30T11:00:00Z'),
        metrics: { recall: 0.8, 'conformance/score': 0.5, 'observed_schema/node_types': 3 },
      },
      { x: Date.parse('2026-10-30T12:00:00Z'), metrics: { 'observed_schema/node_types': 2 } },
    ])
  })

  it('keeps each parameter configuration of an Evaluator apart, never one mixed metric', () => {
    const points = runChartPoints(
      [run({ id: 'a' })],
      [
        evaluation('review', { score: 0.9 }, { subject_id: 'a', parameters: { min_confidence: 0.5 } }),
        evaluation('review', { score: 0.6 }, { subject_id: 'a', parameters: { min_confidence: 0.8 } }),
      ],
    )
    expect(points[0]?.metrics).toEqual({
      'review (min_confidence=0.5)/score': 0.9,
      'review (min_confidence=0.8)/score': 0.6,
    })
  })
})

type Outcome = GateResult['outcomes'][number]

const outcome = (gate: Outcome['gate'], passed: boolean, reasons: string[] = []): Outcome => ({ gate, passed, reasons })

function recorded(outcomes: Outcome[], subjectId = 'r'): GateResult {
  return {
    knowledge_graph: 'support',
    subject_kind: 'construction_run',
    subject_id: subjectId,
    ontology_version: 1,
    passed: outcomes.every((o) => o.passed),
    outcomes,
    evaluated_at: '2026-10-30T12:00:00Z',
  }
}

function preview(outcomes: Outcome[], subjectId = 'r'): GatePreview {
  return {
    knowledge_graph: 'support',
    subject_kind: 'construction_run',
    subject_id: subjectId,
    ontology_version: 1,
    passed: outcomes.every((o) => o.passed),
    outcomes,
    source: { subject_kind: 'construction_run', subject_id: 'g', evaluated_at: '2026-10-30T12:00:00Z' },
  }
}

const conformanceGate = { name: 'conformance-floor', check: 'conformance', min_score: 0.6 }
const reviewGate = {
  name: 'review-score',
  check: 'metric',
  evaluator: 'review',
  metric: 'score',
  min: 0.8,
  parameters: { min_confidence: 0.5, gold: 'v2' },
}
const reviewKey = { kind: 'evaluator', key: 'review (gold="v2", min_confidence=0.5)/score' } as const
const diffGate = { name: 'no-breaking-changes', check: 'ontology_diff', max_classification: 'additive' }
const dropGate = { name: 'no-count-drop', check: 'count_drop', max_drop: 0.5 }

describe('kpiVerdict', () => {
  it('judges Conformance by a conformance Gate, with the origin of the verdict', () => {
    const gating = { preview: preview([outcome(conformanceGate, true, ['Conformance 0.7500 >= 0.6'])]) }
    expect(kpiVerdict({ kind: 'conformance' }, 0.75, gating)).toEqual({
      verdict: 'pass',
      origin: 'preview',
      outcomes: [outcome(conformanceGate, true, ['Conformance 0.7500 >= 0.6'])],
    })
  })

  it('judges the Evaluator metric a metric Gate names by evaluator, metric and parameters, in any order', () => {
    const gating = { preview: preview([outcome(reviewGate, false, ['review.score = 0.6 < min 0.8'])]) }
    expect(kpiVerdict(reviewKey, 0.6, gating)).toMatchObject({ verdict: 'fail', origin: 'preview' })
    expect(kpiVerdict({ kind: 'evaluator', key: 'review (min_confidence=0.8)/score' }, 0.6, gating)).toEqual({
      verdict: 'ungated',
    })
    expect(kpiVerdict({ kind: 'evaluator', key: 'review/score' }, 0.6, gating)).toEqual({ verdict: 'ungated' })
  })

  it('maps a metric Gate without parameters to the plain `<evaluator>/<metric>` key', () => {
    const gate = { name: 'cq', check: 'metric', evaluator: 'competency_question_execution', metric: 'pass_ratio', min: 0.5 }
    const gating = { preview: preview([outcome(gate, true)]) }
    expect(
      kpiVerdict({ kind: 'evaluator', key: 'competency_question_execution/pass_ratio' }, 0.5, gating),
    ).toMatchObject({ verdict: 'pass' })
  })

  it('maps Ontology Diff and count drop Gates to no KPI', () => {
    const gating = { preview: preview([outcome(diffGate, false), outcome(dropGate, false)]) }
    expect(kpiVerdict({ kind: 'conformance' }, 0.75, gating)).toEqual({ verdict: 'ungated' })
    expect(kpiVerdict({ kind: 'evaluator', key: 'observed_schema/node_types' }, 2, gating)).toEqual({ verdict: 'ungated' })
  })

  it('never judges a run metric logged by the pipeline, even one named like a gated KPI', () => {
    const gating = { preview: preview([outcome(conformanceGate, false), outcome(reviewGate, false)]) }
    expect(kpiVerdict({ kind: 'run-metric', key: 'Conformance' }, 0.1, gating)).toEqual({ verdict: 'ungated' })
    expect(kpiVerdict({ kind: 'run-metric', key: reviewKey.key }, 0.1, gating)).toEqual({ verdict: 'ungated' })
  })

  it('takes a recorded Gate result over the Gate Preview', () => {
    const gating = {
      recorded: recorded([outcome(conformanceGate, false, ['Conformance 0.5455 < 0.6'])]),
      preview: preview([outcome(conformanceGate, true)]),
    }
    expect(kpiVerdict({ kind: 'conformance' }, 0.5455, gating)).toEqual({
      verdict: 'fail',
      origin: 'recorded',
      outcomes: [outcome(conformanceGate, false, ['Conformance 0.5455 < 0.6'])],
    })
    // Even when the recorded result's Gates do not cover the KPI.
    const uncovering = { recorded: recorded([outcome(diffGate, true)]), preview: gating.preview }
    expect(kpiVerdict({ kind: 'conformance' }, 0.5455, uncovering)).toEqual({ verdict: 'ungated' })
  })

  it('is "no result" when the covering Gate failed and the run has no value for the KPI', () => {
    const gating = { preview: preview([outcome(reviewGate, false, ['anything at all'])]) }
    expect(kpiVerdict(reviewKey, null, gating)).toEqual({
      verdict: 'no-result',
      origin: 'preview',
      outcomes: [outcome(reviewGate, false, ['anything at all'])],
    })
    expect(kpiVerdict(reviewKey, 0.6, gating)).toMatchObject({ verdict: 'fail' })
  })

  it('fails when any of several Gates on the KPI fails, and passes only when all pass', () => {
    const floor = { ...reviewGate, name: 'floor' }
    const ceiling = { ...reviewGate, name: 'ceiling', max: 0.95 }
    expect(kpiVerdict(reviewKey, 0.97, { preview: preview([outcome(floor, true), outcome(ceiling, false)]) })).toMatchObject({
      verdict: 'fail',
    })
    expect(kpiVerdict(reviewKey, 0.9, { preview: preview([outcome(floor, true), outcome(ceiling, true)]) })).toMatchObject({
      verdict: 'pass',
    })
  })

  it('is ungated for a run that was never gated', () => {
    expect(kpiVerdict({ kind: 'conformance' }, 0.75, {})).toEqual({ verdict: 'ungated' })
  })
})

describe('kpiSummary', () => {
  it('counts the compared runs that pass, fail and have no result for a gated KPI', () => {
    const gate = (passed: boolean) => ({ preview: preview([outcome(reviewGate, passed)]) })
    const verdicts = [
      kpiVerdict(reviewKey, 0.9, gate(true)),
      kpiVerdict(reviewKey, 0.6, gate(false)),
      kpiVerdict(reviewKey, null, gate(false)),
      kpiVerdict(reviewKey, 0.95, gate(true)),
      kpiVerdict(reviewKey, 0.9, {}),
    ]
    expect(kpiSummary(verdicts)).toEqual({ pass: 2, fail: 1, noResult: 1, gated: 4 })
  })

  it('is null when no compared run is gated on the KPI', () => {
    expect(kpiSummary([{ verdict: 'ungated' }, { verdict: 'ungated' }])).toBeNull()
  })
})

describe('gateRows', () => {
  it("lists every Gate, in definition order, with each run's outcome and whether all passed", () => {
    const a = {
      recorded: recorded([outcome(diffGate, true), outcome(conformanceGate, false)], 'a'),
      preview: preview([outcome(conformanceGate, true), outcome(dropGate, true)], 'a'),
    }
    const b = { preview: preview([outcome(conformanceGate, true), outcome(dropGate, false, ['ESCALATED -100%'])], 'b') }
    const rows = gateRows([a, b, {}])
    expect(rows.gates).toEqual([
      {
        name: 'conformance-floor',
        cells: [
          { passed: false, origin: 'recorded', reasons: [] },
          { passed: true, origin: 'preview', reasons: [] },
          null,
        ],
      },
      {
        name: 'no-count-drop',
        cells: [null, { passed: false, origin: 'preview', reasons: ['ESCALATED -100%'] }, null],
      },
      { name: 'no-breaking-changes', cells: [{ passed: true, origin: 'recorded', reasons: [] }, null, null] },
    ])
    expect(rows.overall).toEqual([
      { passed: false, origin: 'recorded' },
      { passed: false, origin: 'preview' },
      null,
    ])
  })
})
