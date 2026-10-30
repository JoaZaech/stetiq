import type { ReactNode } from 'react'
import { type KnowledgeGraphSummary, useKnowledgeGraphs } from '@/api/knowledge-graphs'
import { ErrorAlert } from '@/components/ErrorAlert'
import { NoKnowledgeGraphs } from './NoKnowledgeGraphs'

/** What every view of the Knowledge Graph list says when it fails to load. */
export const KNOWLEDGE_GRAPHS_LOAD_ERROR = 'Could not load the Knowledge Graphs'

interface KnowledgeGraphsLoadedProps {
  /** Shown while the list loads: a skeleton the shape of `children`. */
  pending: ReactNode
  /** The level of the "No Knowledge Graphs yet" heading on the page it sits in. */
  headingLevel?: 2 | 3
  /** Renders the list, which has at least one Knowledge Graph. */
  children: (knowledgeGraphs: KnowledgeGraphSummary[]) => ReactNode
}

/**
 * The readable Knowledge Graphs, once loaded: `pending` until then, an error if they
 * could not be, and how to create the first one when there is none.
 */
export function KnowledgeGraphsLoaded({ pending, headingLevel, children }: KnowledgeGraphsLoadedProps) {
  const knowledgeGraphs = useKnowledgeGraphs()
  if (knowledgeGraphs.isPending) return pending
  if (knowledgeGraphs.isError) return <ErrorAlert error={knowledgeGraphs.error} title={KNOWLEDGE_GRAPHS_LOAD_ERROR} />
  if (knowledgeGraphs.data.length === 0) return <NoKnowledgeGraphs headingLevel={headingLevel} />
  return children(knowledgeGraphs.data)
}
