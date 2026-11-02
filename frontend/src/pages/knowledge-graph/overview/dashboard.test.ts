import { describe, expect, it } from 'vitest'
import type { Promotion } from '@/api/aliases'
import type { GateResult } from '@/api/gate-results'
import type { Observation } from '@/api/observations'
import type { ConstructionRun } from '@/api/runs'
import type { Answerability } from '../use-case/answerability'
import {
  aliasesOf,
  coverageRatio,
  descriptionSummary,
  gatesRatio,
  latestConformance,
  latestDriftFindings,
  ontologySize,
  recentObservations,
  recentPromotions,
  recentRuns,
} from './dashboard'

const run = (id: string, started_at: string, score: number | null = null) =>
  ({ id, started_at, conformance: score === null ? null : { score, mismatches: [] } }) as Pick<
    ConstructionRun,
    'id' | 'started_at' | 'conformance'
  >

const observation = (id: string): Observation => ({
  id,
  knowledge_graph: 'kg',
  run_id: null,
  observed_at: `2026-11-0${id}T10:00:00Z`,
  scope: { database: 'neo4j', label: null, namespace: null },
  baseline_observation_id: id,
  not_comparable: [],
})

describe('runs', () => {
  const runs = [run('a', '2026-11-01'), run('b', '2026-11-03'), run('c', '2026-11-02', 0.9)]

  it('lists the newest first', () => {
    expect(recentRuns(runs, 2).map((r) => r.id)).toEqual(['b', 'c'])
  })

  it("takes the newest run's Conformance that has one", () => {
    expect(latestConformance(runs)).toEqual({ score: 0.9, runId: 'c' })
    expect(latestConformance([run('a', '2026-11-01')])).toBeNull()
  })
})

describe('coverage, Gates and Consumers', () => {
  const answerability: Answerability = {
    questions: 2,
    answerable: 1,
    rows: [
      { id: 'q1', status: 'answerable', missing: [] },
      { id: 'q2', status: 'unanswerable', missing: ['X'] },
    ],
  }

  it('counts answerable questions', () => {
    expect(coverageRatio(answerability)).toEqual({ count: 1, total: 2 })
    expect(coverageRatio(undefined)).toBeNull()
  })

  it("counts the newest version's Gates passed", () => {
    const result = {
      subject_kind: 'ontology_version',
      subject_id: '3',
      evaluated_at: '2026-11-01',
      outcomes: [{ passed: true }, { passed: false }, { passed: true }],
    } as GateResult
    expect(gatesRatio(3, [result])).toEqual({ count: 2, total: 3 })
    expect(gatesRatio(4, [result])).toBeNull()
    expect(gatesRatio(undefined, [result])).toBeNull()
  })

})

describe('Observations', () => {
  const observations = [observation('1'), observation('2')]
  const drift = [{ observation_id: '2', findings: [{}, {}] as never[] }]

  it("counts the latest Observation's Drift findings", () => {
    expect(latestDriftFindings(observations, drift)).toBe(2)
    expect(latestDriftFindings(observations, [])).toBe(0)
    expect(latestDriftFindings([], [])).toBeNull()
  })

  it('lists the newest first, with findings', () => {
    expect(recentObservations(observations, drift).map((o) => [o.observation.id, o.findings])).toEqual([
      ['2', 2],
      ['1', 0],
    ])
  })
})

describe('Promotions', () => {
  it('lists the newest first', () => {
    const promotions = [{ promoted_at: '2026-11-01' }, { promoted_at: '2026-11-03' }] as Promotion[]
    expect(recentPromotions(promotions, 1)).toEqual([{ promoted_at: '2026-11-03' }])
  })
})

describe('the Ontology Version card', () => {
  it('counts Classes, Relations, Attributes on both, and patterns', () => {
    expect(
      ontologySize({
        node_types: [{ label: 'A', properties: [{ name: 'x', type: 'STRING' }] }, { label: 'B' }],
        relationship_types: [{ label: 'R', properties: [{ name: 'since', type: 'DATE' }] }],
        patterns: [['A', 'R', 'B']],
      }),
    ).toEqual({ classes: 2, relations: 1, attributes: 2, patterns: 1 })
  })

  it('names the Aliases pointing to a version', () => {
    expect(
      aliasesOf(
        [
          { name: 'staging', version: 3 },
          { name: 'production', version: 3 },
          { name: 'old', version: 2 },
        ],
        3,
      ),
    ).toEqual(['production', 'staging'])
  })
})

describe('descriptionSummary', () => {
  it('splits off the first sentence from the rest', () => {
    expect(descriptionSummary('Maintenance history of **two** lines. Built by pipeline.py.')).toEqual({
      summary: 'Maintenance history of **two** lines.',
      rest: 'Built by pipeline.py.',
    })
    expect(descriptionSummary('One line only')).toEqual({ summary: 'One line only', rest: '' })
  })

  it('reads only the first paragraph, joining its lines', () => {
    expect(descriptionSummary('First\nline\n\nSecond paragraph.')).toEqual({ summary: 'First line', rest: 'Second paragraph.' })
  })

  it('has nothing for no description', () => {
    expect(descriptionSummary(null)).toBeNull()
    expect(descriptionSummary('  ')).toBeNull()
  })
})
