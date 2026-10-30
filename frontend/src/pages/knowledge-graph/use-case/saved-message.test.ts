import { describe, expect, it } from 'vitest'
import type { SavedUseCase, UseCaseVersion } from '@/api/use-cases'
import { savedMessage } from './saved-message'

const version = (number: number): UseCaseVersion => ({
  knowledge_graph: 'support',
  number,
  content_hash: `hash-${number}`,
  created_at: '2026-01-01T00:00:00+00:00',
  use_case: { competency_questions: [] },
})

const saved = (number: number, created: boolean, latest: number): SavedUseCase => ({
  version: version(number),
  created,
  latest,
})

describe('savedMessage', () => {
  it('names the new Use Case Version', () => {
    expect(savedMessage(saved(4, true, 4))).toBe('Saved as Use Case Version 4.')
  })

  it('says nothing changed when the latest version already has this content', () => {
    expect(savedMessage(saved(3, false, 3))).toBe(
      'Nothing changed: Use Case Version 3 already has this content, so no new version was created.',
    )
  })

  it('explains that content matching an earlier version leaves the latest version in place', () => {
    expect(savedMessage(saved(1, false, 3))).toBe(
      'No new version was created: this content is the same as the earlier Use Case Version 1, ' +
        'and the same content is never registered twice. Use Case Version 3 is still the latest.',
    )
  })
})
