import { useId, type ReactNode } from 'react'
import { Construction } from 'lucide-react'
import type { KnowledgeGraphSection } from '@/app/knowledge-graph-sections'
import { KnowledgeGraphHeader } from './KnowledgeGraphHeader'
import { useKnowledgeGraphName } from './params'

interface KnowledgeGraphSectionPageProps {
  section: KnowledgeGraphSection
  /** Buttons on the section's title row, e.g. Compare or a Table/Chart toggle. */
  actions?: ReactNode
  /** The section's content; a placeholder when omitted (sections not built yet). */
  children?: ReactNode
}

/**
 * The frame of a Knowledge Graph section's landing page: the Knowledge Graph header,
 * then the section title (an `h2`) and its content. `router.tsx` wraps each section's
 * page in it, so a section page renders only its own content.
 */
export function KnowledgeGraphSectionPage({ section, actions, children }: KnowledgeGraphSectionPageProps) {
  const name = useKnowledgeGraphName()
  const id = useId()
  return (
    <>
      <KnowledgeGraphHeader name={name} />
      <section aria-labelledby={id} className="space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 id={id} className="text-base font-semibold">
            {section.label}
          </h2>
          {actions && <div className="flex items-center gap-2">{actions}</div>}
        </div>
        {children ?? <SectionPlaceholder />}
      </section>
    </>
  )
}

function SectionPlaceholder() {
  return (
    <div className="flex items-center gap-2 rounded-lg border border-dashed p-6 text-sm text-muted-foreground">
      <Construction className="size-4" aria-hidden />
      This section is not available yet.
    </div>
  )
}
