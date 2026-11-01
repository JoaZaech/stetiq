import { describe, expect, it } from 'vitest'
import type { ConsumerImpact, QuestionImpact, TaskImpact, UseCaseImpact } from '@/api/consumer-impact'
import type { NodeTypeChange } from '@/api/ontology-diff'
import { causesOf, impactItems, reasonOf } from './consumer-impact'

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

describe('impactItems', () => {
  const task = (description: string, level: TaskImpact['level'], questions: QuestionImpact[] = []): TaskImpact => ({
    id: description.toLowerCase(),
    description,
    level,
    questions,
  })
  const withTasks = (name: string, ...tasks: TaskImpact[]): ConsumerImpact => ({
    ...consumer(name, tasks[0].level),
    tasks,
  })

  it('lists one item per hit Task, by level, then Consumer name, then Task, and the questions no Task needs last', () => {
    const impact: UseCaseImpact = {
      consumers: [
        withTasks('Dashboard', task('Chart', 'will_be_affected')),
        withTasks('Bot', task('Route', 'affected'), task('Guess', 'unknown'), task('Assign', 'affected')),
        withTasks('Agent', task('Sort', 'affected')),
      ],
      no_consumer: [question('names', 'will_be_affected', [deprecated('Agent')]), question('loyal', 'unknown')],
    }

    expect(impactItems(impact).map((i) => [i.level, i.consumer, i.title])).toEqual([
      ['affected', 'Agent', 'Sort'],
      ['affected', 'Bot', 'Assign'],
      ['affected', 'Bot', 'Route'],
      ['will_be_affected', 'Dashboard', 'Chart'],
      ['unknown', 'Bot', 'Guess'],
      ['will_be_affected', null, 'names?'],
      ['unknown', null, 'loyal?'],
    ])
  })

  it("gives a Task's item its questions and the reason they are hit", () => {
    const dates = question('dates', 'affected', [removed('Ticket.opened_at')])
    const names = question('names', 'will_be_affected', [deprecated('Agent')])
    const impact: UseCaseImpact = {
      consumers: [withTasks('Bot', task('Route', 'affected', [dates, names]))],
      no_consumer: [],
    }

    const [item] = impactItems(impact)

    expect(item.questions).toEqual([dates, names])
    expect(item.reason).toBe('breaks Ticket.opened_at; deprecates Agent')
  })

  it('has no items when the Diff hits nothing', () => {
    expect(impactItems({ consumers: [], no_consumer: [] })).toEqual([])
  })
})

describe('reasonOf', () => {
  it('names each Concept once, under its most severe classification', () => {
    expect(
      reasonOf([
        question('a', 'affected', [removed('WorkOrder'), deprecated('PERFORMED_ON')]),
        question('b', 'affected', [removed('PERFORMED_ON'), removed('WorkOrder')]),
      ]),
    ).toBe('breaks WorkOrder, PERFORMED_ON')
  })

  it('names the deprecated Concepts', () => {
    expect(reasonOf([question('names', 'will_be_affected', [deprecated('Agent')])])).toBe('deprecates Agent')
  })

  it("says it can't tell for a question with neither a Concept mapping nor a query", () => {
    expect(reasonOf([question('loyal', 'unknown')])).toBe("can't tell: no Concept mapping or query")
    expect(reasonOf([question('dates', 'affected', [removed('Ticket')]), question('loyal', 'unknown')])).toBe(
      "breaks Ticket; can't tell: no Concept mapping or query",
    )
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
