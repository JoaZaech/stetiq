import { describe, expect, it } from 'vitest'
import type { CompetencyQuestion, UseCase } from '@/api/use-cases'
import { compareUseCases } from './compare'

const NAMES: CompetencyQuestion = {
  id: 'customer-names',
  question: 'What are our customers called?',
  concepts: ['Customer.name'],
}
const TICKETS: CompetencyQuestion = {
  id: 'open-tickets',
  question: 'Which tickets are open?',
  query: 'MATCH (t:Ticket) RETURN t',
}

const useCase = (...questions: CompetencyQuestion[]): UseCase => ({
  competency_questions: questions,
})

describe('compareUseCases', () => {
  it('finds nothing between identical Use Cases', () => {
    expect(compareUseCases(useCase(NAMES, TICKETS), useCase(NAMES, TICKETS))).toEqual({
      description: undefined,
      added: [],
      changed: [],
      removed: [],
    })
  })

  it('lists questions only in the newer version as added, and only in the older as removed', () => {
    const comparison = compareUseCases(useCase(NAMES), useCase(TICKETS))

    expect(comparison.added).toEqual([TICKETS])
    expect(comparison.removed).toEqual([NAMES])
    expect(comparison.changed).toEqual([])
  })

  it('matches questions by id and lists each changed field with both values', () => {
    const comparison = compareUseCases(
      useCase(NAMES, TICKETS),
      useCase(
        { ...NAMES, question: 'What is each customer called?', expected_answer: [{ n: 1 }] },
        TICKETS,
      ),
    )

    expect(comparison.added).toEqual([])
    expect(comparison.removed).toEqual([])
    expect(comparison.changed).toEqual([
      {
        id: 'customer-names',
        fields: [
          {
            field: 'question',
            before: 'What are our customers called?',
            after: 'What is each customer called?',
          },
          { field: 'expected_answer', before: undefined, after: [{ n: 1 }] },
        ],
      },
    ])
  })

  it('compares expected answers and Concept mappings by value', () => {
    const before = { ...NAMES, expected_answer: { a: 1, b: [2] } }
    const reordered = { ...NAMES, concepts: ['Customer.name'], expected_answer: { b: [2], a: 1 } }
    const remapped = { ...NAMES, concepts: ['Customer'], expected_answer: { a: 1, b: [2] } }

    expect(compareUseCases(useCase(before), useCase(reordered)).changed).toEqual([])
    expect(compareUseCases(useCase(before), useCase(remapped)).changed).toEqual([
      {
        id: 'customer-names',
        fields: [{ field: 'concepts', before: ['Customer.name'], after: ['Customer'] }],
      },
    ])
  })

  it('treats a missing Concept mapping like an empty one', () => {
    expect(compareUseCases(useCase({ ...TICKETS, concepts: [] }), useCase(TICKETS)).changed).toEqual(
      [],
    )
  })

  it('reports a changed description', () => {
    const comparison = compareUseCases({ ...useCase(), description: 'Triage' }, useCase())

    expect(comparison.description).toEqual({ before: 'Triage', after: undefined })
  })

  it('orders each list by question id', () => {
    const a = { id: 'a', question: 'A?' }
    const z = { id: 'z', question: 'Z?' }

    expect(compareUseCases(useCase(), useCase(z, a)).added.map((q) => q.id)).toEqual(['a', 'z'])
  })
})
