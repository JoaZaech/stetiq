import { describe, expect, it } from 'vitest'
import type { UseCase } from '@/api/use-cases'
import type { Answerability } from './answerability'
import {
  consumerReadiness,
  consumerReadinessLine,
  neededBy,
  questionsServingNoTask,
  taskReadiness,
  taskReadinessText,
} from './readiness'

const JUDGED: Answerability = {
  questions: 4,
  answerable: 2,
  rows: [
    { id: 'agent-names', status: 'answerable', missing: [] },
    { id: 'customer-names', status: 'answerable', missing: [] },
    { id: 'refunds', status: 'unanswerable', missing: ['Refund'] },
    { id: 'satisfaction', status: 'unmapped', missing: [] },
  ],
}

describe('taskReadiness', () => {
  it('counts how many of the questions a Task needs are answerable, unanswerable or unmapped', () => {
    const task = {
      id: 'route-ticket',
      description: 'Route a ticket',
      competency_questions: ['agent-names', 'customer-names', 'refunds', 'satisfaction'],
    }

    expect(taskReadiness(task, JUDGED)).toEqual({
      total: 4,
      answerable: 2,
      unanswerable: 1,
      unmapped: 1,
    })
  })

  it('is 0 of 0 for a Task that needs no question', () => {
    expect(taskReadiness({ id: 'greet', description: 'Greet' }, JUDGED)).toEqual({
      total: 0,
      answerable: 0,
      unanswerable: 0,
      unmapped: 0,
    })
  })
})

describe('taskReadinessText', () => {
  it('says Ready when every question is answerable, and otherwise why not', () => {
    expect(taskReadinessText({ total: 2, answerable: 2, unanswerable: 0, unmapped: 0 })).toBe('Ready')
    expect(taskReadinessText({ total: 0, answerable: 0, unanswerable: 0, unmapped: 0 })).toBe('Ready')
    expect(taskReadinessText({ total: 4, answerable: 2, unanswerable: 1, unmapped: 1 })).toBe(
      "Not ready: 1 unanswerable, 1 can't check",
    )
    expect(taskReadinessText({ total: 1, answerable: 0, unanswerable: 0, unmapped: 1 })).toBe(
      "Not ready: 1 can't check",
    )
  })
})

describe('consumerReadiness', () => {
  const ready = { id: 'greet', description: 'Greet', competency_questions: ['customer-names'] }
  const blocked = { id: 'refund', description: 'Refund', competency_questions: ['customer-names', 'refunds'] }
  const unchecked = { id: 'survey', description: 'Survey', competency_questions: ['satisfaction'] }

  it('counts the Tasks whose questions are all answerable: success only when all are', () => {
    const all = consumerReadiness({ id: 'bot', name: 'Bot', tasks: [ready] }, JUDGED)
    expect(all).toEqual({ state: 'checked', ready: 1, tasks: 1 })
    expect(consumerReadinessLine(all)).toEqual({ tone: 'success', label: '1 of 1 Tasks ready' })

    const some = consumerReadiness({ id: 'bot', name: 'Bot', tasks: [ready, blocked, unchecked] }, JUDGED)
    expect(some).toEqual({ state: 'checked', ready: 1, tasks: 3 })
    expect(consumerReadinessLine(some)).toEqual({ tone: 'failure', label: '1 of 3 Tasks ready' })
  })

  it('is not checked yet without a judged result, which is neutral, never a pass', () => {
    const readiness = consumerReadiness({ id: 'bot', name: 'Bot', tasks: [ready] }, undefined)
    expect(readiness).toEqual({ state: 'not-checked' })
    expect(consumerReadinessLine(readiness)).toEqual({ tone: 'neutral', label: 'Not checked yet' })
  })

  it('says No Tasks for a Consumer without Tasks, judged or not', () => {
    for (const answerability of [JUDGED, undefined]) {
      const readiness = consumerReadiness({ id: 'bot', name: 'Bot', tasks: [] }, answerability)
      expect(consumerReadinessLine(readiness)).toEqual({ tone: 'neutral', label: 'No Tasks' })
    }
    expect(consumerReadiness({ id: 'bot', name: 'Bot' }, JUDGED)).toEqual({ state: 'no-tasks' })
  })
})

describe('questionsServingNoTask', () => {
  const useCase: UseCase = {
    competency_questions: [
      { id: 'agent-names', question: 'What are our agents called?' },
      { id: 'customer-names', question: 'What are our customers called?' },
      { id: 'refunds', question: 'Which tickets were refunded?' },
    ],
    consumers: [
      {
        id: 'bot',
        name: 'Bot',
        tasks: [
          { id: 'route', description: 'Route', competency_questions: ['customer-names'] },
          { id: 'greet', description: 'Greet' },
        ],
      },
      {
        id: 'dashboard',
        name: 'Dashboard',
        tasks: [{ id: 'show', description: 'Show', competency_questions: ['customer-names', 'refunds'] }],
      },
    ],
  }

  it('lists the questions no Consumer’s Task needs', () => {
    expect([...questionsServingNoTask(useCase)]).toEqual(['agent-names'])
  })

  it('names each Consumer and Task that needs a question, in Consumer order', () => {
    expect(
      neededBy(useCase, 'customer-names').map(({ consumer, task }) => `${consumer.name} · ${task.description}`),
    ).toEqual(['Bot · Route', 'Dashboard · Show'])
    expect(neededBy(useCase, 'agent-names')).toEqual([])
  })

  it('lists every question of a Use Case without Consumers', () => {
    expect([...questionsServingNoTask({ competency_questions: useCase.competency_questions })]).toEqual([
      'agent-names',
      'customer-names',
      'refunds',
    ])
  })
})
