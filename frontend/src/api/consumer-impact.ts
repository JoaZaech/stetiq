import { useQuery } from '@tanstack/react-query'
import { ApiError, api, kgPath } from './client'
import type { OntologyChange } from './ontology-diff'

/**
 * How an Ontology Diff hits a Competency Question, Task or Consumer (impact.py), the most
 * severe first: a breaking change makes it affected, a deprecating one will-be-affected,
 * and a question only a question mapper could map is unknown.
 */
export const IMPACT_LEVELS = ['affected', 'will_be_affected', 'unknown'] as const

export type ImpactLevel = (typeof IMPACT_LEVELS)[number]

/** wire.use_case_impact_to_json: a question a change hits, and the changes that hit it (none when unknown). */
export interface QuestionImpact {
  id: string
  question: string
  level: ImpactLevel
  changes: OntologyChange[]
}

export interface TaskImpact {
  id: string
  description: string
  level: ImpactLevel
  /** Only the questions a change hits, in the Task's order. */
  questions: QuestionImpact[]
}

export interface ConsumerImpact {
  id: string
  name: string
  kind: string | null
  /** The most severe of its Tasks'. */
  level: ImpactLevel
  /** Only the Tasks a change hits. */
  tasks: TaskImpact[]
}

/** The Consumers an Ontology Diff hits (only those), and the hit questions no Task needs. */
export interface UseCaseImpact {
  consumers: ConsumerImpact[]
  no_consumer: QuestionImpact[]
}

export const consumerImpactQueryKeys = {
  one: (kg: string, base: number, target: number) => ['consumer-impact', kg, base, target] as const,
}

/**
 * `GET …/consumer-impact?base=&target=`: the Consumer impact of the Ontology Diff from
 * version `base` to `target`, judged against the latest Use Case Version. Fails with a
 * `NoUseCaseError` (see `isNoUseCase`) when the Knowledge Graph has no Use Case.
 */
export const consumerImpactQuery = (kg: string, base: number, target: number) => ({
  queryKey: consumerImpactQueryKeys.one(kg, base, target),
  queryFn: () => api<UseCaseImpact>(`${kgPath(kg)}/consumer-impact?base=${base}&target=${target}`),
})

export const useConsumerImpact = (kg: string, base: number, target: number) =>
  useQuery({
    ...consumerImpactQuery(kg, base, target),
    enabled: Number.isInteger(base) && Number.isInteger(target),
  })

/** True when the request failed because the Knowledge Graph has no Use Case to judge impact by. */
export const isNoUseCase = (error: unknown): boolean =>
  error instanceof ApiError && error.type === 'NoUseCaseError'
