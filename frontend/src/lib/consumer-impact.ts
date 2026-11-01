/**
 * How the Consumer impact of an Ontology Diff is laid out for display, wherever it is shown
 * (the Ontology Diff views, and the Promotion confirmation): a flat list of items.
 */
import { IMPACT_LEVELS, type ImpactLevel, type QuestionImpact, type UseCaseImpact } from '@/api/consumer-impact'
import { type Classification, compareSeverity, type OntologyChange } from '@/api/ontology-diff'

/** How the UI names each impact level. */
export const IMPACT_LABEL: Record<ImpactLevel, string> = {
  affected: 'Affected',
  will_be_affected: 'Will be affected',
  unknown: 'Impact unknown',
}

/**
 * One line of Consumer impact: a hit Task, or a hit question no Task needs (`consumer`
 * null). `key` tells items apart and is never shown.
 */
export interface ImpactItem {
  key: string
  level: ImpactLevel
  /** The Task's description, or the question's text. */
  title: string
  /** The Consumer's name; null for a question no Task needs. */
  consumer: string | null
  reason: string
  /** The questions it hits, in the Task's order. */
  questions: QuestionImpact[]
}

const byLevel = (a: ImpactLevel, b: ImpactLevel) => IMPACT_LEVELS.indexOf(a) - IMPACT_LEVELS.indexOf(b)

/**
 * The impact as one item per hit Task, sorted by level (affected first), then Consumer
 * name, then Task description; then one item per hit question no Task needs, last, sorted
 * by level, then question.
 */
export function impactItems(impact: UseCaseImpact): ImpactItem[] {
  const tasks = impact.consumers
    .flatMap((consumer) =>
      consumer.tasks.map((task) => ({
        key: `${consumer.id}/${task.id}`,
        level: task.level,
        title: task.description,
        consumer: consumer.name,
        reason: reasonOf(task.questions),
        questions: task.questions,
      })),
    )
    .sort(
      (a, b) =>
        byLevel(a.level, b.level) || a.consumer.localeCompare(b.consumer) || a.title.localeCompare(b.title),
    )
  const unneeded = impact.no_consumer
    .map((q) => ({
      key: q.id,
      level: q.level,
      title: q.question,
      consumer: null,
      reason: reasonOf([q]),
      questions: [q],
    }))
    .sort((a, b) => byLevel(a.level, b.level) || a.title.localeCompare(b.title))
  return [...tasks, ...unneeded]
}

/**
 * Why `questions` are hit, in one line: the Concepts a breaking change hits ("breaks …"),
 * then those a deprecating one hits ("deprecates …"), each Concept once at its most severe,
 * and "can't tell" when a question states neither a Concept mapping nor a query.
 */
export function reasonOf(questions: QuestionImpact[]): string {
  const causes = causesOfChanges(questions.flatMap((q) => q.changes))
  const named = (classification: Classification) =>
    causes.filter((c) => c.classification === classification).map((c) => c.concept)
  const breaks = named('breaking')
  const deprecates = named('deprecating')
  return [
    breaks.length > 0 && `breaks ${breaks.join(', ')}`,
    deprecates.length > 0 && `deprecates ${deprecates.join(', ')}`,
    questions.some((q) => q.level === 'unknown') && "can't tell: no Concept mapping or query",
  ]
    .filter(Boolean)
    .join('; ')
}

/** A Concept whose changes hit a question, at the most severe of their classifications. */
export interface Cause {
  concept: string
  classification: Classification
}

/** The Concepts whose changes hit `question`, each once, the most severe first. */
export const causesOf = (question: QuestionImpact): Cause[] => causesOfChanges(question.changes)

function causesOfChanges(changes: OntologyChange[]): Cause[] {
  const worst = new Map<string, Classification>()
  for (const { concept, classification } of changes) {
    const seen = worst.get(concept)
    if (seen === undefined || compareSeverity(classification, seen) > 0) worst.set(concept, classification)
  }
  return [...worst]
    .map(([concept, classification]) => ({ concept, classification }))
    .sort((a, b) => compareSeverity(b.classification, a.classification))
}
