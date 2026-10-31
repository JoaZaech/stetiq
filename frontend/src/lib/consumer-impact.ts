/**
 * How the Consumer impact of an Ontology Diff is grouped for display, wherever it is shown
 * (the Ontology Diff views, and the Promotion confirmation).
 */
import {
  type ConsumerImpact,
  IMPACT_LEVELS,
  type ImpactLevel,
  type QuestionImpact,
  type UseCaseImpact,
} from '@/api/consumer-impact'
import { type Classification, compareSeverity } from '@/api/ontology-diff'

/** How the UI names each impact level. */
export const IMPACT_LABEL: Record<ImpactLevel, string> = {
  affected: 'Affected',
  will_be_affected: 'Will be affected',
  unknown: 'Impact unknown',
}

/** One level's Consumers, and the questions at that level no Task needs. */
export interface ImpactSection {
  level: ImpactLevel
  consumers: ConsumerImpact[]
  noConsumer: QuestionImpact[]
}

/**
 * The impact a section per level, affected first, then will-be-affected, then unknown;
 * a level with nothing in it has no section. Consumers keep the server's order; each
 * Consumer's Tasks are listed the most severe first.
 */
export function impactSections(impact: UseCaseImpact): ImpactSection[] {
  const bySeverity = (a: { level: ImpactLevel }, b: { level: ImpactLevel }) =>
    IMPACT_LEVELS.indexOf(a.level) - IMPACT_LEVELS.indexOf(b.level)
  return IMPACT_LEVELS.map((level) => ({
    level,
    consumers: impact.consumers
      .filter((c) => c.level === level)
      .map((c) => ({ ...c, tasks: [...c.tasks].sort(bySeverity) })),
    noConsumer: impact.no_consumer.filter((q) => q.level === level),
  })).filter((s) => s.consumers.length > 0 || s.noConsumer.length > 0)
}

/** A Concept whose changes hit a question, at the most severe of their classifications. */
export interface Cause {
  concept: string
  classification: Classification
}

/** The Concepts whose changes hit `question`, each once, the most severe first. */
export function causesOf(question: QuestionImpact): Cause[] {
  const worst = new Map<string, Classification>()
  for (const { concept, classification } of question.changes) {
    const seen = worst.get(concept)
    if (seen === undefined || compareSeverity(classification, seen) > 0) worst.set(concept, classification)
  }
  return [...worst]
    .map(([concept, classification]) => ({ concept, classification }))
    .sort((a, b) => compareSeverity(b.classification, a.classification))
}
