import { describe, expect, it } from 'vitest'
import type { Answerability } from '../use-case/answerability'
import { consumerGateNext, consumersNext, gateNext, knowledgeGraphNext, upstreamNext } from './pipeline-next'

describe('upstreamNext', () => {
  it('asks for a first run, then points at a failed one', () => {
    expect(upstreamNext('kg', undefined)).toEqual({ kind: 'command', label: 'Track a run', command: 'stetiq run' })
    expect(upstreamNext('kg', { id: 'abcdef123456', status: 'failed' })).toEqual({
      kind: 'link',
      label: 'Why run abcdef12 failed',
      to: '/kg/kg/runs/abcdef123456/evaluation',
    })
    expect(upstreamNext('kg', { id: 'x', status: 'finished' })).toBeUndefined()
  })
})

describe('gateNext', () => {
  it('asks to evaluate an ungated version, or opens the failed Gates', () => {
    expect(gateNext('kg', 3, 'none')).toMatchObject({ kind: 'command', command: 'stetiq gate kg --version 3' })
    expect(gateNext('kg', 3, 'failed')).toMatchObject({ kind: 'link', to: '/kg/kg/versions/3' })
    expect(gateNext('kg', 3, 'passed')).toBeUndefined()
    expect(gateNext('kg', undefined, 'none')).toBeUndefined()
  })
})

describe('knowledgeGraphNext', () => {
  it('asks for a first Observation, or opens the latest one’s findings', () => {
    expect(knowledgeGraphNext('kg', undefined, null)).toMatchObject({ command: 'stetiq observe kg' })
    expect(knowledgeGraphNext('kg', 'o1', 4)).toEqual({
      kind: 'link',
      label: 'Review 4 Drift findings',
      to: '/kg/kg/observations?sheet=observation%3Ao1',
    })
    expect(knowledgeGraphNext('kg', 'o1', 0)).toBeUndefined()
  })
})

describe('consumerGateNext', () => {
  it('follows the step’s status', () => {
    expect(consumerGateNext('kg', 'None declared')).toMatchObject({ to: '/kg/kg/use-case?tab=consumers' })
    expect(consumerGateNext('kg', 'Not evaluated yet')).toMatchObject({ command: 'stetiq consumer gate kg' })
    expect(consumerGateNext('kg', 'Passed')).toBeUndefined()
  })
})

describe('consumersNext', () => {
  const answerability = (...statuses: ('answerable' | 'unanswerable' | 'unmapped')[]): Answerability => ({
    questions: statuses.length,
    answerable: statuses.filter((s) => s === 'answerable').length,
    rows: statuses.map((status, i) => ({ id: `q${i}`, status, missing: [] })),
  })

  it('points at the unanswerable questions first, then those it can’t check', () => {
    expect(consumersNext('kg', answerability('unanswerable', 'unmapped'))).toEqual({
      kind: 'link',
      label: '1 question unanswerable',
      to: '/kg/kg/use-case?status=unanswerable',
    })
    expect(consumersNext('kg', answerability('answerable', 'unmapped', 'unmapped'))).toMatchObject({
      label: "2 questions can't be checked",
      to: '/kg/kg/use-case?status=unmapped',
    })
    expect(consumersNext('kg', answerability('answerable'))).toBeUndefined()
  })
})
