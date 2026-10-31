import { describe, expect, it } from 'vitest'
import type { UseCase } from '@/api/use-cases'
import {
  consumerDraftOf,
  EMPTY_CONSUMER_DRAFT,
  EMPTY_TASK_DRAFT,
  taskDraftOf,
  validateConsumerDraft,
  validateTaskDraft,
  withConsumer,
  withoutConsumer,
  withoutTask,
  withTask,
  type ConsumerDraft,
  type TaskDraft,
} from './consumer-form'

// The support_use_case_consumers seed's Use Case, as the server sends it.
const useCase: UseCase = {
  competency_questions: [
    { id: 'agent-names', question: 'What are our agents called?' },
    { id: 'customer-names', question: 'What are our customers called?' },
  ],
  consumers: [
    {
      id: 'triage-bot',
      name: 'Triage bot',
      tasks: [
        { id: 'greet-customer', description: 'Greet the customer by name', competency_questions: ['customer-names'] },
        {
          id: 'route-ticket',
          description: 'Route a new ticket to an agent',
          competency_questions: ['agent-names', 'customer-names'],
        },
      ],
    },
    { id: 'workload-dashboard', name: 'Workload dashboard', tasks: [{ id: 'show-agents', description: 'List the agents on shift' }] },
  ],
}

const consumerDraft = (fields: Partial<ConsumerDraft>): ConsumerDraft => ({
  ...EMPTY_CONSUMER_DRAFT,
  id: 'billing-app',
  name: 'Billing app',
  ...fields,
})

describe('validateConsumerDraft', () => {
  it('accepts a new Consumer with only an id and a name', () => {
    expect(validateConsumerDraft(consumerDraft({}), useCase)).toEqual({})
  })

  it('needs an id and a name', () => {
    expect(validateConsumerDraft(consumerDraft({ id: ' ', name: '' }), useCase)).toEqual({
      id: 'Needs an id.',
      name: 'Needs a name.',
    })
  })

  it('refuses an id another Consumer, a Task or a Competency Question has', () => {
    expect(validateConsumerDraft(consumerDraft({ id: 'workload-dashboard' }), useCase)).toEqual({
      id: 'The Consumer workload-dashboard already has this id.',
    })
    expect(validateConsumerDraft(consumerDraft({ id: 'route-ticket' }), useCase)).toEqual({
      id: 'The Task route-ticket already has this id.',
    })
    expect(validateConsumerDraft(consumerDraft({ id: 'agent-names' }), useCase)).toEqual({
      id: 'The Competency Question agent-names already has this id.',
    })
  })

  it('accepts the edited Consumer keeping its own id', () => {
    expect(validateConsumerDraft(consumerDraft({ id: 'triage-bot', name: 'Bot' }), useCase, 'triage-bot')).toEqual({})
  })
})

describe('withConsumer', () => {
  it('adds a new Consumer, sorted by id, omitting blank optional fields', () => {
    const next = withConsumer(useCase, consumerDraft({ kind: ' application ', contact: '' }))
    expect(next.consumers?.map((c) => c.id)).toEqual(['billing-app', 'triage-bot', 'workload-dashboard'])
    expect(next.consumers?.[0]).toEqual({ id: 'billing-app', name: 'Billing app', kind: 'application' })
    expect(next.competency_questions).toBe(useCase.competency_questions)
  })

  it('edits a Consumer, keeping its Tasks', () => {
    const draft = consumerDraftOf(useCase.consumers![0])
    expect(draft).toEqual({ id: 'triage-bot', name: 'Triage bot', kind: '', contact: '', description: '' })
    const next = withConsumer(useCase, { ...draft, contact: 'Ada Lovelace' })
    expect(next.consumers?.[0]).toEqual({ ...useCase.consumers![0], contact: 'Ada Lovelace' })
    expect(next.consumers).toHaveLength(2)
  })
})

describe('withoutConsumer', () => {
  it('removes a Consumer with its Tasks, keeping the Competency Questions', () => {
    const next = withoutConsumer(useCase, 'triage-bot')
    expect(next.consumers?.map((c) => c.id)).toEqual(['workload-dashboard'])
    expect(next.competency_questions).toEqual(useCase.competency_questions)
  })

  it('leaves out the consumers key once the last Consumer is gone', () => {
    const next = withoutConsumer(withoutConsumer(useCase, 'triage-bot'), 'workload-dashboard')
    expect(next).toEqual({ competency_questions: useCase.competency_questions })
  })
})

const taskDraft = (fields: Partial<TaskDraft>): TaskDraft => ({
  ...EMPTY_TASK_DRAFT,
  id: 'count-agents',
  description: 'Count the agents on shift',
  ...fields,
})

describe('validateTaskDraft', () => {
  it('accepts a new Task with an id and a description, needing no question', () => {
    expect(validateTaskDraft(taskDraft({}), useCase)).toEqual({})
  })

  it('needs an id and a description', () => {
    expect(validateTaskDraft(taskDraft({ id: '', description: ' ' }), useCase)).toEqual({
      id: 'Needs an id.',
      description: 'Needs a description.',
    })
  })

  it('refuses an id another Task, a Consumer or a Competency Question has', () => {
    expect(validateTaskDraft(taskDraft({ id: 'greet-customer' }), useCase).id).toBe(
      'The Task greet-customer already has this id.',
    )
    expect(validateTaskDraft(taskDraft({ id: 'triage-bot' }), useCase).id).toBe(
      'The Consumer triage-bot already has this id.',
    )
    expect(validateTaskDraft(taskDraft({ id: 'customer-names' }), useCase).id).toBe(
      'The Competency Question customer-names already has this id.',
    )
    expect(validateTaskDraft(taskDraft({ id: 'show-agents' }), useCase, 'show-agents')).toEqual({})
  })
})

describe('withTask', () => {
  it('adds a Task under a Consumer, sorted by id, with its questions sorted', () => {
    const next = withTask(
      useCase,
      'triage-bot',
      taskDraft({ competency_questions: ['customer-names', 'agent-names'] }),
    )
    expect(next.consumers?.[0].tasks).toEqual([
      { id: 'count-agents', description: 'Count the agents on shift', competency_questions: ['agent-names', 'customer-names'] },
      ...useCase.consumers![0].tasks!,
    ])
    expect(next.consumers?.[1]).toBe(useCase.consumers![1])
  })

  it('edits a Task, omitting competency_questions once it needs none', () => {
    const route = useCase.consumers![0].tasks![1]
    const draft = taskDraftOf(route)
    expect(draft).toEqual({
      id: 'route-ticket',
      description: 'Route a new ticket to an agent',
      competency_questions: ['agent-names', 'customer-names'],
    })
    const next = withTask(useCase, 'triage-bot', { ...draft, description: ' Route a ticket ', competency_questions: [] })
    expect(next.consumers?.[0].tasks?.[1]).toEqual({ id: 'route-ticket', description: 'Route a ticket' })
  })
})

describe('withoutTask', () => {
  it('removes a Task, leaving out the tasks key once the Consumer has none', () => {
    const next = withoutTask(useCase, 'show-agents')
    expect(next.consumers?.[1]).toEqual({ id: 'workload-dashboard', name: 'Workload dashboard' })
    expect(next.consumers?.[0]).toBe(useCase.consumers![0])
  })
})
