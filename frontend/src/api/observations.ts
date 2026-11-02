import { useQuery } from '@tanstack/react-query'
import { api, kgPath } from './client'
import type { Conformance, Mismatch, MismatchSubjectKind } from './runs'

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
  /**
   * On-demand only: the Observation its Violation Rates were compared with (its own id
   * when it is the first since the contract's Ontology Version became the contract).
   */
  baseline_observation_id: string | null
  /** The Drift checks that lacked their input, so raised no finding. */
  not_comparable: NotComparable[]
  /**
   * An on-demand Observation's Conformance to `ontology_version`, the Contract Alias's
   * version when it was made. Null for a run-end Observation (its run holds its
   * Conformance) and for one made before Observations were scored.
   */
  conformance: Conformance | null
  ontology_version: number | null
}

/**
 * wire.alignment_point_to_json: one Conformance score on the alignment trend. A
 * Construction Run's (`run_id` set; `observation_id` is the Observation it ended with) or
 * an on-demand Observation's; `ontology_version` is the version it was judged against.
 */
export interface AlignmentPoint {
  at: string
  score: number
  ontology_version: number
  observation_id: string
  run_id: string | null
}

/**
 * drift.DriftThresholds; null = check off. The count ones are fractions of the previous
 * count (0.1 = 10%), `max_violation_increase` is absolute points above the baseline's
 * Violation Rate (0.01 = 1 point). Events from before that check lack it.
 */
export interface DriftThresholds {
  max_count_drop: number | null
  max_count_increase: number | null
  max_violation_increase?: number | null
}

/** drift.DriftKind */
export type DriftKind =
  | 'undeclared'
  | 'vanished'
  | 'undeclared_value'
  | 'count_drop'
  | 'count_increase'
  | 'violation_increase'

/** drift.DriftFinding */
export interface DriftFinding {
  kind: DriftKind
  subject: string
  subject_kind: MismatchSubjectKind
  detail: string
  previous_count: number | null
  observed_count: number | null
  /** `undeclared_value` only: the value outside the contract's Vocabulary. */
  value?: string
  /** `undeclared_value` only: how many owners hold the value, and their share (absent when unknown). */
  count?: number
  share?: number
  /** `violation_increase` only: the Conformance check, and its Violation Rate in the baseline and now. */
  violation?: Mismatch['kind']
  baseline_rate?: number
  observed_rate?: number
  /** `violation_increase` of a `cardinality_violation` only: which degree of the pattern. */
  direction?: 'out' | 'in'
}

/** drift.NotComparable: a check that lacked its input, so it raised no finding. */
export interface NotComparable {
  /** The finding kind the check would have raised. */
  check: DriftKind
  subject: string
  subject_kind: MismatchSubjectKind
  reason: string
  /** For a Violation Rate: the Conformance check behind it. */
  violation?: Mismatch['kind']
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

/** Query keys of Observations and Drift events. */
export const observationQueryKeys = {
  all: (kg: string) => ['observations', kg] as const,
  one: (id: string | null) => ['observation', id] as const,
  driftEvents: (kg: string) => ['drift-events', kg] as const,
  alignmentTrend: (kg: string) => ['alignment-trend', kg] as const,
}

/** The Knowledge Graph's Observations, oldest first. */
export const observationsQuery = (kg: string) => ({
  queryKey: observationQueryKeys.all(kg),
  queryFn: () => api<Observation[]>(kgPath(kg) + '/observations'),
})
export const useObservations = (kg: string) => useQuery(observationsQuery(kg))

/** The Knowledge Graph's Drift events, oldest first. */
export const driftEventsQuery = (kg: string) => ({
  queryKey: observationQueryKeys.driftEvents(kg),
  queryFn: () => api<DriftEvent[]>(kgPath(kg) + '/drift-events'),
})
export const useDriftEvents = (kg: string) => useQuery(driftEventsQuery(kg))

/** The alignment trend: run and on-demand Conformance scores, oldest first. */
export const alignmentTrendQuery = (kg: string) => ({
  queryKey: observationQueryKeys.alignmentTrend(kg),
  queryFn: () => api<AlignmentPoint[]>(kgPath(kg) + '/alignment-trend'),
})
export const useAlignmentTrend = (kg: string) => useQuery(alignmentTrendQuery(kg))

/** The Observed Schema (graph_source.ObservedSchema); the run page reads only its sizes. */
export interface ObservedSchema {
  node_types: unknown[]
  relationship_types: unknown[]
  patterns: unknown[]
}

/** wire.observation_to_json in full: with its Observed Schema (the wire key is `schema`). */
export interface ObservationWithObservedSchema extends Observation {
  schema: ObservedSchema
}

/** One Observation, e.g. the one a Construction Run ended with; idle while `id` is null. */
export const useObservation = (id: string | null) =>
  useQuery({
    queryKey: observationQueryKeys.one(id),
    queryFn: () => api<ObservationWithObservedSchema>(`/observations/${encodeURIComponent(id ?? '')}`),
    enabled: id !== null,
  })
