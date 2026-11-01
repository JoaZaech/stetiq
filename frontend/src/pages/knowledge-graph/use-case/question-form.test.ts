import { describe, expect, it } from 'vitest'
import type { UseCase } from '@/api/use-cases'
import {
  EMPTY_DRAFT,
  serverErrorField,
  tasksNeeding,
  validateDraft,
  withoutQuestion,
  type QuestionDraft,
} from './question-form'

const draft = (fields: Partial<QuestionDraft>): QuestionDraft => ({
  ...EMPTY_DRAFT,
  id: 'ticket-dates',
  question: 'When was each ticket opened?',
  ...fields,
})

// A Use Case with a question, a Consumer and a Task, as the server sends it.
const useCase: UseCase = {
  competency_questions: [
    { id: 'customer-names', question: 'What are our customers called?' },
    { id: 'ticket-dates', question: 'When was each ticket opened?' },
  ],
  consumers: [
    {
      id: 'triage-bot',
      name: 'Triage bot',
      tasks: [{ id: 'route-ticket', description: 'Route a new ticket', competency_questions: ['customer-names'] }],
    },
  ],
}

const empty: UseCase = { competency_questions: [] }

describe('validateDraft', () => {
  it('accepts a question with only an id and a question', () => {
    expect(validateDraft(draft({}), empty)).toEqual({})
  })

  it('accepts every Concept-reference form, one per line or comma-separated', () => {
    const concepts = 'Customer\nTicket.opened_at, (Customer)-[OPENED]->(Ticket)\n()-[OPENED|FILED]-()'
    expect(validateDraft(draft({ concepts, expected_answer: '[{"a": 1}]' }), empty)).toEqual({})
  })

  it('needs an id and a question', () => {
    expect(validateDraft(draft({ id: ' ', question: '' }), empty)).toEqual({
      id: 'Needs an id.',
      question: 'Needs the question in natural language.',
    })
  })

  it('refuses an id another question, a Consumer or a Task already has', () => {
    expect(validateDraft(draft({ id: 'customer-names' }), useCase)).toEqual({
      id: 'The Competency Question customer-names already has this id.',
    })
    expect(validateDraft(draft({ id: 'triage-bot' }), useCase)).toEqual({
      id: 'The Consumer triage-bot already has this id.',
    })
    expect(validateDraft(draft({ id: 'route-ticket' }), useCase)).toEqual({
      id: 'The Task route-ticket already has this id.',
    })
  })

  it('accepts the id of the question being edited', () => {
    expect(validateDraft(draft({}), useCase, 'ticket-dates')).toEqual({})
  })

  it('refuses an expected answer that is not JSON', () => {
    const errors = validateDraft(draft({ expected_answer: "[{opened_at: '2026'}]" }), empty)
    expect(Object.keys(errors)).toEqual(['expected_answer'])
    expect(errors.expected_answer).toMatch(/^Not valid JSON/)
  })

  it('names each malformed Concept reference', () => {
    expect(validateDraft(draft({ concepts: 'Customer\nTicket.\n(Customer)->(Ticket)' }), empty)).toEqual({
      concepts: 'Not a Concept reference: "Ticket.", "(Customer)->(Ticket)".',
    })
  })
})

describe('serverErrorField', () => {
  it('finds the field a Use Case validation error names', () => {
    expect(serverErrorField('competency_questions[1].query: must be a non-empty Cypher string')).toBe('query')
    expect(serverErrorField('ticket-dates.expected_answer: must be a JSON value')).toBe('expected_answer')
    expect(serverErrorField("ticket-dates.concepts: 'x y' is not a Concept reference")).toBe('concepts')
    expect(serverErrorField('ticket-dates: duplicate competency question id')).toBe('id')
    expect(serverErrorField('triage-bot: consumer id is already a competency question id')).toBe('id')
  })

  it('finds no field in an error about the whole Use Case', () => {
    expect(serverErrorField('competency_questions: needs at least one question')).toBeUndefined()
  })
})

describe('withoutQuestion', () => {
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

  it('names the Tasks that need a question', () => {
    expect(tasksNeeding(useCase, 'customer-names').map((t) => t.id)).toEqual(['greet-customer', 'route-ticket'])
    expect(tasksNeeding(useCase, 'agent-names').map((t) => t.id)).toEqual(['route-ticket'])
    expect(tasksNeeding({ competency_questions: [] }, 'agent-names')).toEqual([])
  })

  it('takes the question off every Task that needs it, keeping the Tasks', () => {
    expect(withoutQuestion(useCase, 'customer-names')).toEqual({
      competency_questions: [{ id: 'agent-names', question: 'What are our agents called?' }],
      consumers: [
        {
          id: 'triage-bot',
          name: 'Triage bot',
          tasks: [
            { id: 'greet-customer', description: 'Greet the customer by name' },
            { id: 'route-ticket', description: 'Route a new ticket to an agent', competency_questions: ['agent-names'] },
          ],
        },
        useCase.consumers![1],
      ],
    })
  })
})
