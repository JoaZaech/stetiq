import { useQuery } from '@tanstack/react-query'
import { api, kgPath } from './client'
import type { GateResult } from './gate-results'

/**
 * wire.gate_preview_to_json: the latest used Gates judged against one Construction Run by
 * the server on request, never recorded (ADR 0007). A recorded Gate result about the
 * same run wins over it.
 */
export interface GatePreview {
  knowledge_graph: string
  subject_kind: 'construction_run'
  subject_id: string
  ontology_version: number
  passed: boolean
  outcomes: GateResult['outcomes']
  /** The recorded Gate result whose Gate definitions were used. */
  source: { subject_kind: GateResult['subject_kind']; subject_id: string; evaluated_at: string }
}

export const gatePreviewQueryKeys = {
  all: (kg: string) => ['gate-previews', kg] as const,
}

/** One Gate Preview per Construction Run; `[]` when the Knowledge Graph was never gated. */
export const gatePreviewsQuery = (kg: string) => ({
  queryKey: gatePreviewQueryKeys.all(kg),
  queryFn: () => api<GatePreview[]>(kgPath(kg) + '/gate-previews'),
})
export const useGatePreviews = (kg: string) => useQuery(gatePreviewsQuery(kg))

/** The Gate Preview of one Construction Run, or undefined when it has none. */
export function runGatePreview(previews: readonly GatePreview[], runId: string): GatePreview | undefined {
  return previews.find((p) => p.subject_id === runId)
}
