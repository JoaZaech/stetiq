import { useQuery } from '@tanstack/react-query'
import { useOntologyVersions, versionEvaluationsQuery } from '@/api/ontology-versions'
import { answerabilityOf, type Answerability } from './answerability'

/** How far the latest Ontology Version has been judged against a Use Case Version. */
export type LatestAnswerability =
  | { state: 'pending' }
  | { state: 'error'; error: Error }
  /** The Knowledge Graph has no Ontology Version. */
  | { state: 'no-ontology' }
  | { state: 'not-judged'; ontologyVersion: number }
  | { state: 'judged'; ontologyVersion: number; answerability: Answerability }

/**
 * Whether the latest Ontology Version can answer `useCaseVersion`'s Competency Questions,
 * from its stored structural answerability result (saving a new Use Case Version judges
 * it). The Competency Questions list and the Competency Question sheet share the queries.
 */
export function useLatestAnswerability(knowledgeGraph: string, useCaseVersion: number): LatestAnswerability {
  const versions = useOntologyVersions(knowledgeGraph)
  const latest = versions.data?.at(-1)?.number
  const results = useQuery({
    ...versionEvaluationsQuery(knowledgeGraph, latest ?? 0),
    enabled: latest !== undefined,
  })
  if (versions.isError) return { state: 'error', error: versions.error }
  if (versions.isPending) return { state: 'pending' }
  if (latest === undefined) return { state: 'no-ontology' }
  if (results.isError) return { state: 'error', error: results.error }
  if (results.isPending) return { state: 'pending' }
  const answerability = answerabilityOf(results.data, useCaseVersion)
  return answerability
    ? { state: 'judged', ontologyVersion: latest, answerability }
    : { state: 'not-judged', ontologyVersion: latest }
}
