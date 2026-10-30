import { useQuery } from '@tanstack/react-query'
import { api, kgPath } from './client'

/** wire.graph_source_scope_to_json: a database, optionally narrowed by label or namespace. */
export interface GraphSourceScope {
  database: string
  label: string | null
  namespace: string | null
}

/** `database neo4j · label Support`; the label and namespace only when narrowed. */
export function formatScope(scope: GraphSourceScope): string {
  return [
    `database ${scope.database}`,
    scope.label && `label ${scope.label}`,
    scope.namespace && `namespace ${scope.namespace}`,
  ]
    .filter(Boolean)
    .join(' · ')
}

/** wire.observation_to_json, without the Observed Schema (no page shows it yet). */
export interface Observation {
  id: string
  knowledge_graph: string
  /** The Construction Run that ended with this Observation; null for an on-demand one. */
  run_id: string | null
  observed_at: string
  scope: GraphSourceScope
}

/** drift.DriftThresholds: fractions of the previous count (0.1 = 10%); null = check off. */
export interface DriftThresholds {
  max_count_drop: number | null
  max_count_increase: number | null
}

/** drift.DriftFinding */
export interface DriftFinding {
  kind: 'undeclared' | 'vanished' | 'count_drop' | 'count_increase'
  subject: string
  subject_kind: 'node_type' | 'relationship_type' | 'property'
  detail: string
  previous_count: number | null
  observed_count: number | null
}

/** wire.drift_event_to_json */
export interface DriftEvent {
  id: string
  knowledge_graph: string
  observation_id: string
  previous_observation_id: string | null
  contract_alias: string
  ontology_version: number
  detected_at: string
  findings: DriftFinding[]
  thresholds: DriftThresholds
}

/** The Knowledge Graph's Observations, oldest first. */
export const observationsQuery = (kg: string) => ({
  queryKey: ['observations', kg],
  queryFn: () => api<Observation[]>(kgPath(kg) + '/observations'),
})
export const useObservations = (kg: string) => useQuery(observationsQuery(kg))

/** The Knowledge Graph's Drift events, oldest first. */
export const driftEventsQuery = (kg: string) => ({
  queryKey: ['drift-events', kg],
  queryFn: () => api<DriftEvent[]>(kgPath(kg) + '/drift-events'),
})
export const useDriftEvents = (kg: string) => useQuery(driftEventsQuery(kg))

/** wire.observation_to_json in full; the run page reads only the Observed Schema's sizes. */
export interface ObservationWithSchema extends Observation {
  schema: { node_types: unknown[]; relationship_types: unknown[]; patterns: unknown[] }
}

/** One Observation, e.g. the one a Construction Run ended with; idle while `id` is null. */
export const useObservation = (id: string | null) =>
  useQuery({
    queryKey: ['observation', id],
    queryFn: () => api<ObservationWithSchema>(`/observations/${encodeURIComponent(id ?? '')}`),
    enabled: id !== null,
  })
