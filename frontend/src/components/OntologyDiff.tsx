import type { ReactNode } from 'react'
import {
  type Classification,
  type OntologyChange,
  type OntologyDiff,
  useOntologyDiff,
} from '@/api/ontology-diff'
import { ErrorAlert } from '@/components/ErrorAlert'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { cn } from '@/lib/utils'

/** Most severe first; the Diff colours are used for nothing else in the app. */
const CLASSIFICATIONS: readonly Classification[] = ['breaking', 'deprecating', 'additive']

const CLASSIFICATION_STYLE: Record<Classification, string> = {
  additive: 'border-diff-additive/40 bg-diff-additive/10 text-diff-additive',
  deprecating: 'border-diff-deprecating/40 bg-diff-deprecating/10 text-diff-deprecating',
  breaking: 'border-diff-breaking/40 bg-diff-breaking/10 text-diff-breaking',
}

interface OntologyDiffPanelProps {
  knowledgeGraph: string
  base: number
  target: number
  /** One line above the Diff, e.g. "Changes from v3". */
  caption?: ReactNode
}

/**
 * Loads and shows the Ontology Diff from version `base` to `target`: the Changes tab,
 * and the Promote dialog (against the version the Alias points to now).
 */
export function OntologyDiffPanel({
  knowledgeGraph,
  base,
  target,
  caption,
}: OntologyDiffPanelProps) {
  const diff = useOntologyDiff(knowledgeGraph, base, target)
  if (diff.isError) return <ErrorAlert error={diff.error} />
  if (diff.isPending) return <Skeleton className="h-32 w-full" />
  return <OntologyDiffView diff={diff.data} base={base} target={target} caption={caption} />
}

interface OntologyDiffViewProps {
  diff: OntologyDiff
  base: number
  target: number
  caption?: ReactNode
}

/**
 * An Ontology Diff that is already loaded: the overall classification, a count per
 * classification, and every change labelled additive, deprecating or breaking (most
 * severe first). A region named "Ontology Diff".
 */
export function OntologyDiffView({ diff, base, target, caption }: OntologyDiffViewProps) {
  const changes = bySeverity(diff.changes)
  return (
    <section aria-label="Ontology Diff" className="space-y-4">
      {caption && <p className="text-sm text-muted-foreground">{caption}</p>}
      {diff.classification === null ? (
        <p className="text-sm text-muted-foreground">
          No changes between v{base} and v{target}.
        </p>
      ) : (
        <>
          <div className="flex flex-wrap items-center gap-x-4 gap-y-2 text-sm">
            <p className="font-medium">
              Overall: <ClassificationBadge classification={diff.classification} />
            </p>
            <p className="text-muted-foreground">
              {CLASSIFICATIONS.map((c) => ({
                c,
                n: changes.filter((x) => x.classification === c).length,
              }))
                .filter(({ n }) => n > 0)
                .map(({ c, n }) => `${n} ${c}`)
                .join(' · ')}
            </p>
          </div>
          <Table aria-label="Changes">
            <TableHeader>
              <TableRow>
                <TableHead>Classification</TableHead>
                <TableHead>Change</TableHead>
                <TableHead>Concept</TableHead>
                <TableHead>Detail</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {changes.map((change) => (
                <TableRow key={`${change.concept_kind}:${change.concept}:${change.detail}`}>
                  <TableCell>
                    <ClassificationBadge classification={change.classification} />
                  </TableCell>
                  <TableCell>{change.kind}</TableCell>
                  <TableCell className="font-mono text-xs">{change.concept}</TableCell>
                  <TableCell>{change.detail}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </>
      )}
    </section>
  )
}

/** A change's (or a whole Diff's) classification, in its Diff colour. */
export function ClassificationBadge({ classification }: { classification: Classification }) {
  return (
    <Badge variant="outline" className={cn(CLASSIFICATION_STYLE[classification])}>
      {classification}
    </Badge>
  )
}

function bySeverity(changes: OntologyChange[]): OntologyChange[] {
  const rank = (c: OntologyChange) => CLASSIFICATIONS.indexOf(c.classification)
  return [...changes].sort((a, b) => rank(a) - rank(b))
}
