import { describe, expect, it } from 'vitest'
import type { ConsumerImpact, QuestionImpact, UseCaseImpact } from '@/api/consumer-impact'
import type { NodeTypeChange } from '@/api/ontology-diff'
import { causesOf, impactSections } from './consumer-impact'

const removed = (label: string): NodeTypeChange => ({
  concept: label,
  concept_kind: 'node_type',
  kind: 'removed',
  classification: 'breaking',
  detail: `node type ${label} removed`,
})
const deprecated = (label: string): NodeTypeChange => ({
  concept: label,
  concept_kind: 'node_type',
  kind: 'deprecated',
  classification: 'deprecating',
  detail: 'deprecated',
})

const question = (id: string, level: QuestionImpact['level'], changes: NodeTypeChange[] = []): QuestionImpact => ({
  id,
  question: `${id}?`,
  level,
  changes,
})

const consumer = (id: string, level: ConsumerImpact['level']): ConsumerImpact => ({
  id,
  name: id,
  kind: null,
  level,
  tasks: [{ id: `${id}-task`, description: 'Work', level, questions: [question(`${id}-q`, level)] }],
})

describe('impactSections', () => {
  it('groups Consumers and unassigned questions by level, affected first, and leaves out empty levels', () => {
    const impact: UseCaseImpact = {
      consumers: [consumer('dashboard', 'will_be_affected'), consumer('bot', 'affected'), consumer('crm', 'affected')],
      no_consumer: [question('loyal', 'unknown'), question('names', 'will_be_affected', [deprecated('Agent')])],
    }

    expect(
      impactSections(impact).map((s) => ({
        level: s.level,
        consumers: s.consumers.map((c) => c.id),
        noConsumer: s.noConsumer.map((q) => q.id),
      })),
    ).toEqual([
      { level: 'affected', consumers: ['bot', 'crm'], noConsumer: [] },
      { level: 'will_be_affected', consumers: ['dashboard'], noConsumer: ['names'] },
      { level: 'unknown', consumers: [], noConsumer: ['loyal'] },
    ])
  })

  it("lists a Consumer's Tasks the most severe first, keeping their order otherwise", () => {
    const bot: ConsumerImpact = {
      ...consumer('bot', 'affected'),
      tasks: [
        { id: 'assign', description: 'Assign', level: 'will_be_affected', questions: [] },
        { id: 'guess', description: 'Guess', level: 'unknown', questions: [] },
        { id: 'route', description: 'Route', level: 'affected', questions: [] },
        { id: 'sort', description: 'Sort', level: 'affected', questions: [] },
      ],
    }

    const [section] = impactSections({ consumers: [bot], no_consumer: [] })

    expect(section.consumers[0].tasks.map((t) => t.id)).toEqual(['route', 'sort', 'assign', 'guess'])
  })

  it('has no sections when the Diff hits nothing', () => {
    expect(impactSections({ consumers: [], no_consumer: [] })).toEqual([])
  })
})

describe('causesOf', () => {
  it('names each Concept that hits a question once, with its most severe classification, the most severe first', () => {
    const q = question('handlers', 'affected', [
      deprecated('Agent'),
      removed('HANDLES'),
      { ...removed('Agent'), kind: 'changed', detail: 'parent Party -> (none)' },
    ])

    expect(causesOf(q)).toEqual([
      { concept: 'Agent', classification: 'breaking' },
      { concept: 'HANDLES', classification: 'breaking' },
    ])
  })

  it('names the deprecated Concepts of a will-be-affected question', () => {
    expect(causesOf(question('names', 'will_be_affected', [deprecated('Agent')]))).toEqual([
      { concept: 'Agent', classification: 'deprecating' },
    ])
  })
})
