import type { Mismatch } from '@/api/runs'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { formatMetric } from '@/lib/format'
import { Panel } from '../versions/OverviewTab'
import { useConstructionRunTab } from './run-context'

const SUBJECT_KIND: Record<Mismatch['subject_kind'], string> = {
  node_type: 'class',
  relationship_type: 'relation',
  property: 'attribute',
  pattern: 'pattern',
}

const MISMATCH_KIND: Record<Mismatch['kind'], string> = {
  absent: 'Declared but not observed',
  undeclared: 'Observed but not declared',
  type_mismatch: 'Undeclared value type',
  required_missing: 'Required but not always set',
}

/**
 * The run page's Conformance tab: the score, then each mismatch. Concepts declared
 * but not observed and observed but not declared get a table each (as
 * `Conformance.declared_absent` / `undeclared` split them); endpoint patterns and
 * attribute value mismatches are listed after them.
 */
export function RunConformanceTab() {
  const run = useConstructionRunTab()
  const conformance = run.conformance
  if (conformance === null) {
    return (
      <p className="text-sm text-muted-foreground">
        No Conformance: it is assessed when the run ends with an Observation of its Graph Source.
      </p>
    )
  }
  const concept = (kind: Mismatch['kind']) =>
    conformance.mismatches.filter((m) => m.kind === kind && m.subject_kind !== 'pattern')
  const absent = concept('absent')
  const undeclared = concept('undeclared')
  const other = conformance.mismatches.filter((m) => !absent.includes(m) && !undeclared.includes(m))
  return (
    <div className="space-y-8">
      <Panel title="Score">
        <p className="text-2xl font-semibold tabular-nums">{formatMetric(conformance.score)}</p>
        <p className="text-sm text-muted-foreground">
          The share of checked classes, relations, attributes and patterns that are both declared
          and observed, with no mismatch.
        </p>
      </Panel>
      <MismatchTable title="Declared but not observed" mismatches={absent} />
      <MismatchTable title="Observed but not declared" mismatches={undeclared} />
      {other.length > 0 && <MismatchTable title="Other mismatches" mismatches={other} showKind />}
    </div>
  )
}

function MismatchTable({
  title,
  mismatches,
  showKind = false,
}: {
  title: string
  mismatches: Mismatch[]
  showKind?: boolean
}) {
  return (
    <Panel title={title}>
      {mismatches.length === 0 ? (
        <p className="text-sm text-muted-foreground">None.</p>
      ) : (
        <Table aria-label={title}>
          <TableHeader>
            <TableRow>
              <TableHead>{showKind ? 'Subject' : 'Concept'}</TableHead>
              <TableHead>Kind</TableHead>
              {showKind && <TableHead>Mismatch</TableHead>}
              <TableHead>Detail</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {[...mismatches]
              .sort((a, b) => a.subject.localeCompare(b.subject))
              .map((m) => (
                <TableRow key={`${m.subject_kind}/${m.subject}/${m.kind}`}>
                  <TableCell className="font-mono text-xs">{m.subject}</TableCell>
                  <TableCell>{SUBJECT_KIND[m.subject_kind]}</TableCell>
                  {showKind && <TableCell>{MISMATCH_KIND[m.kind]}</TableCell>}
                  <TableCell className="text-muted-foreground">{m.detail}</TableCell>
                </TableRow>
              ))}
          </TableBody>
        </Table>
      )}
    </Panel>
  )
}
