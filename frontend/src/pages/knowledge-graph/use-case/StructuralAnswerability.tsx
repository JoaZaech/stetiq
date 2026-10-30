import { useId } from 'react'
import { useOntologyVersions, useVersionEvaluations } from '@/api/ontology-versions'
import { ErrorAlert } from '@/components/ErrorAlert'
import { Skeleton } from '@/components/ui/skeleton'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { answerabilityOf, type AnswerabilityStatus } from './answerability'

const STATUS_LABELS: Record<AnswerabilityStatus, string> = {
  answerable: 'Answerable',
  unanswerable: 'Unanswerable',
  unmapped: 'Unmapped',
}

interface StructuralAnswerabilityProps {
  knowledgeGraph: string
  useCaseVersion: number
}

/**
 * Whether the latest Ontology Version can answer a Use Case Version's Competency
 * Questions, from its stored structural answerability result (saving a new Use Case
 * Version judges it).
 */
export function StructuralAnswerability({ knowledgeGraph, useCaseVersion }: StructuralAnswerabilityProps) {
  const id = useId()
  const versions = useOntologyVersions(knowledgeGraph)
  const latest = versions.data?.at(-1)
  return (
    <section aria-labelledby={id} className="min-w-0 space-y-3">
      <h3 id={id} className="text-sm font-semibold">
        Structural answerability
      </h3>
      {versions.isError ? (
        <ErrorAlert error={versions.error} />
      ) : versions.isPending ? (
        <Skeleton className="h-16 w-full" />
      ) : latest ? (
        <Judged knowledgeGraph={knowledgeGraph} ontologyVersion={latest.number} useCaseVersion={useCaseVersion} />
      ) : (
        <p className="text-sm text-muted-foreground">This Knowledge Graph has no Ontology Version yet.</p>
      )}
    </section>
  )
}

function Judged({
  knowledgeGraph,
  ontologyVersion,
  useCaseVersion,
}: StructuralAnswerabilityProps & { ontologyVersion: number }) {
  const results = useVersionEvaluations(knowledgeGraph, ontologyVersion)
  if (results.isError) return <ErrorAlert error={results.error} />
  if (results.isPending) return <Skeleton className="h-16 w-full" />
  const answerability = answerabilityOf(results.data, useCaseVersion)
  if (!answerability) {
    return (
      <p className="text-sm text-muted-foreground">
        Ontology Version v{ontologyVersion} has not been judged against Use Case Version {useCaseVersion}{' '}
        yet. Saving a change to the Competency Questions judges it.
      </p>
    )
  }
  return (
    <>
      <p className="text-sm">
        Ontology Version v{ontologyVersion} answers {answerability.answerable} of {answerability.questions}{' '}
        Competency Questions of Use Case Version {useCaseVersion}.
      </p>
      <div className="overflow-hidden rounded-lg border">
        <Table aria-label="Structural answerability">
          <TableHeader>
            <TableRow>
              <TableHead>Competency Question</TableHead>
              <TableHead>Status</TableHead>
              <TableHead>Missing Concepts</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {answerability.rows.map((row) => (
              <TableRow key={row.id}>
                <TableCell>
                  <code className="font-mono text-xs">{row.id}</code>
                </TableCell>
                <TableCell>{STATUS_LABELS[row.status]}</TableCell>
                <TableCell className="font-mono text-xs">
                  {row.missing.length ? row.missing.join(', ') : <span className="text-muted-foreground">—</span>}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
    </>
  )
}
