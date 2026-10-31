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

describe('validateDraft', () => {
  it('accepts a question with only an id and a question', () => {
    expect(validateDraft(draft({}), [])).toEqual({})
  })

  it('accepts every Concept-reference form, one per line or comma-separated', () => {
    const concepts = 'Customer\nTicket.opened_at, (Customer)-[OPENED]->(Ticket)\n()-[OPENED|FILED]-()'
    expect(validateDraft(draft({ concepts, expected_answer: '[{"a": 1}]' }), [])).toEqual({})
  })

  it('needs an id and a question', () => {
    expect(validateDraft(draft({ id: ' ', question: '' }), [])).toEqual({
      id: 'Needs an id.',
      question: 'Needs the question in natural language.',
    })
  })

  it('refuses an id another question already has', () => {
    expect(validateDraft(draft({}), ['customer-names', 'ticket-dates'])).toEqual({
      id: 'Another Competency Question already has the id ticket-dates.',
    })
  })

  it('refuses an expected answer that is not JSON', () => {
    const errors = validateDraft(draft({ expected_answer: "[{opened_at: '2026'}]" }), [])
    expect(Object.keys(errors)).toEqual(['expected_answer'])
    expect(errors.expected_answer).toMatch(/^Not valid JSON/)
  })

  it('names each malformed Concept reference', () => {
    expect(validateDraft(draft({ concepts: 'Customer\nTicket.\n(Customer)->(Ticket)' }), [])).toEqual({
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
