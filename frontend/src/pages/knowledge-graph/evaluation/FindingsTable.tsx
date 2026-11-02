import { useMemo, useState } from 'react'
import { FilterMenu } from '@/components/FilterMenu'
import { ListCount } from '@/components/ListToolbar'
import { SearchInput } from '@/components/SearchInput'
import { StatusIcon } from '@/components/StatusLabel'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { facetCounts, filterFindings, type FindingRow } from './findings'

/**
 * The one findings table every evaluation shares (a run's Conformance mismatches, an
 * Observation's Drift): Concept · Kind · Finding · Change, filterable by kind and
 * finding. `initialFinding` opens it filtered, e.g. from a failed run's banner.
 */
export function FindingsTable({
  rows,
  initialFinding = '',
  empty = 'No findings.',
}: {
  rows: readonly FindingRow[]
  initialFinding?: string
  empty?: string
}) {
  const [kind, setKind] = useState('')
  const [finding, setFinding] = useState(initialFinding)
  const [query, setQuery] = useState('')
  const kinds = useMemo(() => facetCounts(rows, 'kind'), [rows])
  const findings = useMemo(() => facetCounts(rows, 'finding'), [rows])
  const shown = useMemo(() => filterFindings(rows, { kind, finding, query }), [rows, kind, finding, query])

  if (rows.length === 0) return <p className="text-sm text-muted-foreground">{empty}</p>
  return (
    <section aria-label="Findings" className="space-y-2">
      <div className="flex flex-wrap items-center gap-2">
        <SearchInput label="Search findings" value={query} onChange={setQuery} className="w-56" />
        <FilterMenu label="Finding" value={finding} options={findings} onChange={setFinding} />
        <FilterMenu label="Kind" value={kind} options={kinds} onChange={setKind} />
      </div>
      <Table aria-label="Findings">
        <TableHeader>
          <TableRow>
            <TableHead>Concept</TableHead>
            <TableHead>Kind</TableHead>
            <TableHead>Finding</TableHead>
            <TableHead>Change</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {shown.length === 0 ? (
            <TableRow>
              <TableCell colSpan={4} className="text-muted-foreground">
                No finding matches these filters.
              </TableCell>
            </TableRow>
          ) : (
            shown.map((row, i) => (
              <TableRow key={`${row.finding}/${row.kind}/${row.subject}/${row.change}/${i}`}>
                <TableCell className="font-mono text-xs">{row.subject}</TableCell>
                <TableCell>{row.kind}</TableCell>
                <TableCell>
                  <span className="inline-flex items-center gap-1.5">
                    <StatusIcon tone={row.tone} label={row.finding} />
                    {row.finding}
                  </span>
                </TableCell>
                <TableCell className="text-muted-foreground tabular-nums">{row.change}</TableCell>
              </TableRow>
            ))
          )}
        </TableBody>
      </Table>
      <ListCount shown={shown.length} total={rows.length} noun="findings" />
    </section>
  )
}
