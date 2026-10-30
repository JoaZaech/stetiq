import type { MouseEvent, ReactNode } from 'react'
import { LocateFixed } from 'lucide-react'
import { useSearchParams } from 'react-router'
import { Button } from '@/components/ui/button'
import { formatCount } from '@/lib/format'
import { formatSelection, SELECT_PARAM } from './concept-selection'
import { attributeGroupId, type TableConcept, useTableLinks } from './table-links'

/** A plain click, which the Table handles; any other (e.g. to open a new tab) the browser does. */
const plainClick = (e: MouseEvent) => e.button === 0 && !e.metaKey && !e.ctrlKey && !e.shiftKey && !e.altKey

const LINK = 'underline-offset-2 hover:underline focus-visible:underline'

/**
 * A class or relation name that links to its row: clicking selects it (`?select=`) and
 * scrolls to its row. Its href is the same page with it selected, so it opens in a new tab.
 */
export function ConceptLink({ concept, children }: { concept: TableConcept; children?: ReactNode }) {
  const links = useTableLinks()
  const [params] = useSearchParams()
  const href = new URLSearchParams(params)
  href.set(SELECT_PARAM, formatSelection(concept))
  return (
    <a
      href={`?${href}`}
      className={LINK}
      onClick={(e) => {
        if (!plainClick(e)) return
        e.preventDefault()
        links.select(concept)
      }}
    >
      {children ?? concept.label}
    </a>
  )
}

/** A class's or relation's attribute count, linking to its owner's group in the Attributes grid. */
export function AttributeCountLink({
  owner,
  count,
  children,
}: {
  owner: string
  /** How many attributes its group lists. */
  count: number
  children: ReactNode
}) {
  const links = useTableLinks()
  return (
    <a
      href={`#${attributeGroupId(owner)}`}
      aria-label={formatCount(count, 'attribute')}
      className={LINK}
      onClick={(e) => {
        if (!plainClick(e)) return
        e.preventDefault()
        links.openGroup(owner)
      }}
    >
      {children}
    </a>
  )
}

/** A row's "Show on Map": switches to the Map with `concept` selected and centred. */
export function ShowOnMap({ concept }: { concept: TableConcept }) {
  const links = useTableLinks()
  return (
    <Button
      variant="ghost"
      size="icon"
      className="size-7 text-muted-foreground"
      aria-label={`Show ${concept.label} on Map`}
      title="Show on Map"
      onClick={() => links.showOnMap(concept)}
    >
      <LocateFixed aria-hidden className="size-4" />
    </Button>
  )
}
