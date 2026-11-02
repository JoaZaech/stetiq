import { describe, expect, it } from 'vitest'
import type { ConsumerGateResult } from '@/api/consumer-gate-results'
import type { GateResult } from '@/api/gate-results'
import type { Consumer } from '@/api/use-cases'
import type { Answerability } from '../use-case/answerability'
import {
  consumerGateStatus,
  consumersStatus,
  gateStatus,
  knowledgeGraphStatus,
  upstreamStatus,
} from './pipeline-status'

const NOW = new Date('2026-11-01T12:00:00Z')

describe('upstreamStatus', () => {
  const run = (status: 'running' | 'finished' | 'failed', started_at: string, ended_at: string | null) => ({
    status,
    started_at,
    ended_at,
  })

  it('is neutral without a run', () => {
    expect(upstreamStatus([], NOW)).toEqual({ tone: 'neutral', status: 'No runs' })
  })

  it("shows the latest run's status and how long ago it ended", () => {
    const runs = [
      run('finished', '2026-11-01T11:50:00Z', '2026-11-01T11:55:00Z'),
      run('failed', '2026-10-30T12:00:00Z', '2026-10-30T12:05:00Z'),
    ]
    expect(upstreamStatus(runs, NOW)).toEqual({ tone: 'success', status: 'Finished', fact: '5 minutes ago' })
    expect(upstreamStatus([run('failed', '2026-11-01T09:00:00Z', '2026-11-01T10:00:00Z')], NOW)).toEqual({
      tone: 'failure',
      status: 'Failed',
      fact: '2 hours ago',
    })
  })

  it('says when a running run started', () => {
    expect(upstreamStatus([run('running', '2026-11-01T11:58:00Z', null)], NOW)).toEqual({
      tone: 'running',
      status: 'Running',
      fact: 'started 2 minutes ago',
    })
  })
})

describe('gateStatus', () => {
  const outcome = (passed: boolean) => ({ gate: { name: 'g' }, passed, reasons: [] })
  const result = (subject_id: string, evaluated_at: string, outcomes: boolean[]): GateResult => ({
    knowledge_graph: 'support',
    subject_kind: 'ontology_version',
    subject_id,
    ontology_version: Number(subject_id),
    passed: outcomes.every(Boolean),
    outcomes: outcomes.map(outcome),
    evaluated_at,
  })

  it('is neutral "Not gated" without a version, or when the newest version was never gated', () => {
    expect(gateStatus(undefined, [])).toEqual({ tone: 'neutral', status: 'Not gated' })
    expect(gateStatus(3, [result('2', '2026-11-01T10:00:00Z', [true])])).toEqual({
      tone: 'neutral',
      status: 'Not gated',
      fact: 'v3',
    })
  })

  it("shows the newest version's latest Gate result", () => {
    const results = [
      result('3', '2026-11-01T09:00:00Z', [true, true]),
      result('3', '2026-11-01T10:00:00Z', [false, true, false]),
    ]
    expect(gateStatus(3, results)).toEqual({ tone: 'failure', status: 'Failed', fact: 'v3 · 2 of 3 Gates failed' })
    expect(gateStatus(3, [results[0]])).toEqual({ tone: 'success', status: 'Passed', fact: 'v3 · All 2 Gates passed' })
  })

  it("ignores a run's Gate result", () => {
    const run = { ...result('3', '2026-11-01T10:00:00Z', [false]), subject_kind: 'construction_run' as const }
    expect(gateStatus(3, [run]).status).toBe('Not gated')
  })
})

describe('knowledgeGraphStatus', () => {
  const contract = { alias: 'production', version: 3 }
  const observations = [
    { id: 'o1', observed_at: '2026-10-31T12:00:00Z' },
    { id: 'o2', observed_at: '2026-11-01T11:00:00Z' },
  ]

  it('is neutral "Not observed" without an Observation, with where the Contract Alias points', () => {
    expect(knowledgeGraphStatus(contract, [], [], NOW)).toEqual({
      tone: 'neutral',
      status: 'Not observed',
      fact: 'production → v3',
    })
    expect(knowledgeGraphStatus({ alias: 'production', version: undefined }, [], [], NOW).fact).toBe(
      'production (not set)',
    )
  })

  it('has no Drift when the latest Observation raised none, even if an earlier one did', () => {
    expect(knowledgeGraphStatus(contract, observations, [{ observation_id: 'o1' }], NOW)).toEqual({
      tone: 'success',
      status: 'No Drift',
      fact: 'production → v3 · observed 1 hour ago',
    })
  })

  it('warns of Drift found by the latest Observation', () => {
    expect(knowledgeGraphStatus(contract, observations, [{ observation_id: 'o2' }], NOW)).toEqual({
      tone: 'warning',
      status: 'Drift',
      fact: 'production → v3 · observed 1 hour ago',
    })
  })
})

describe('consumerGateStatus', () => {
  const gate = { name: 'rows-hold', check: 'row_count_drop', task: 't', max_drop: 0.1 }
  const gated = (id: string): Consumer => ({ id, name: id, consumer_gates: [gate] })
  const verdict = (consumer: string, passed: boolean) => ({ consumer, passed }) as ConsumerGateResult

  it('is neutral when no Consumer declares a Consumer Gate', () => {
    expect(consumerGateStatus([], [])).toEqual({ tone: 'neutral', status: 'None declared' })
    expect(consumerGateStatus([{ id: 'bot', name: 'Bot' }], [verdict('bot', false)])).toEqual({
      tone: 'neutral',
      status: 'None declared',
    })
  })

  it('fails when any latest verdict failed, counting every Consumer that declares one', () => {
    const consumers = [gated('a'), gated('b'), gated('c'), { id: 'd', name: 'd' }]
    const results = [verdict('a', true), verdict('b', true), verdict('b', false)]
    expect(consumerGateStatus(consumers, results)).toEqual({ tone: 'failure', status: 'Failed', fact: '1 of 3 passed', ratio: { count: 1, total: 3 } })
  })

  it('passes only when every latest verdict passed', () => {
    const results = [verdict('a', false), verdict('a', true), verdict('b', true)]
    expect(consumerGateStatus([gated('a'), gated('b')], results)).toEqual({
      tone: 'success',
      status: 'Passed',
      fact: '2 of 2 passed',
      ratio: { count: 2, total: 2 },
    })
  })

  it('is neutral while a Consumer Gate was never evaluated and none failed', () => {
    expect(consumerGateStatus([gated('a'), gated('b')], [verdict('a', true)])).toEqual({
      tone: 'neutral',
      status: 'Not evaluated yet',
      fact: '1 of 2 passed',
      ratio: { count: 1, total: 2 },
    })
  })
})

describe('consumersStatus', () => {
  const answerability: Answerability = {
    questions: 2,
    answerable: 1,
    rows: [
      { id: 'yes', status: 'answerable', missing: [] },
      { id: 'no', status: 'unanswerable', missing: ['Refund'] },
    ],
  }
  const consumer = (id: string, ...questions: string[][]): Consumer => ({
    id,
    name: id,
    tasks: questions.map((qs, i) => ({ id: `${id}-${i}`, description: '', competency_questions: qs })),
  })

  it('is neutral without Consumers, or when none has a Task', () => {
    expect(consumersStatus([], answerability)).toEqual({ tone: 'neutral', status: 'No Consumers' })
    expect(consumersStatus([{ id: 'a', name: 'a' }], answerability)).toEqual({ tone: 'neutral', status: 'No Tasks' })
  })

  it('is neutral "Not checked yet" when the latest Ontology Version was not judged', () => {
    expect(consumersStatus([consumer('a', ['yes'])], undefined)).toEqual({
      tone: 'neutral',
      status: 'Not checked yet',
    })
  })

  it('is ready when every Consumer with Tasks is ready for all of them; one without Tasks does not count', () => {
    const consumers = [consumer('a', ['yes']), consumer('b', [], ['yes']), { id: 'c', name: 'c' }]
    expect(consumersStatus(consumers, answerability)).toEqual({ tone: 'success', status: 'Ready', fact: '2 of 2 ready', ratio: { count: 2, total: 2 } })
  })

  it('is not ready when a Consumer has a Task the version is not ready for', () => {
    const consumers = [consumer('a', ['yes']), consumer('b', ['yes'], ['no']), consumer('c', ['no'])]
    expect(consumersStatus(consumers, answerability)).toEqual({
      tone: 'failure',
      status: 'Not ready',
      fact: '1 of 3 ready',
      ratio: { count: 1, total: 3 },
    })
  })
})
