import { describe, expect, it } from 'vitest'
import type { UseCase } from '@/api/use-cases'
import type { Answerability } from './answerability'
import { questionsServingNoTask, taskReadiness } from './readiness'

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

  it('lists every question of a Use Case without Consumers', () => {
    expect([...questionsServingNoTask({ competency_questions: useCase.competency_questions })]).toEqual([
      'agent-names',
      'customer-names',
      'refunds',
    ])
  })
})
