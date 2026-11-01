import type { Task } from '@/api/use-cases'
import { useOntologyVersions, useVersionEvaluations } from '@/api/ontology-versions'
import { answerabilityOf } from './answerability'
import { taskReadiness } from './readiness'

interface TaskReadinessProps {
  knowledgeGraph: string
  /** The Use Case Version the Task belongs to: readiness reads the result judged against it. */
  useCaseVersion: number
  task: Task
}

/**
 * How many of a Task's Competency Questions the latest Ontology Version answers ("3/4
 * questions answerable on v5"), and how many of the rest are unanswerable or unmapped,
 * from its stored structural answerability result. Shows nothing while loading or when
 * the Knowledge Graph has no Ontology Version; the queries are shared with the
 * Structural answerability section, which shows errors.
 */
export function TaskReadiness({ knowledgeGraph, useCaseVersion, task }: TaskReadinessProps) {
  const versions = useOntologyVersions(knowledgeGraph)
  const latest = versions.data?.at(-1)?.number
  if (latest === undefined) return null
  return (
    <Judged knowledgeGraph={knowledgeGraph} useCaseVersion={useCaseVersion} task={task} ontologyVersion={latest} />
  )
}

function Judged({
  knowledgeGraph,
  useCaseVersion,
  task,
  ontologyVersion,
}: TaskReadinessProps & { ontologyVersion: number }) {
  const results = useVersionEvaluations(knowledgeGraph, ontologyVersion)
  if (!results.data) return null
  const answerability = answerabilityOf(results.data, useCaseVersion)
  const readiness = answerability && taskReadiness(task, answerability)
  if (readiness?.total === 0) return null
  return (
    <div role="group" aria-label={`Readiness of ${task.id}`} className="flex flex-wrap gap-x-2 text-xs">
      {readiness ? (
        <>
          <span className="font-medium">
            {readiness.answerable}/{readiness.total} questions answerable on v{ontologyVersion}
          </span>
          {readiness.unanswerable > 0 && (
            <span className="text-destructive">{readiness.unanswerable} unanswerable</span>
          )}
          {readiness.unmapped > 0 && (
            <span className="text-muted-foreground">{readiness.unmapped} unmapped</span>
          )}
        </>
      ) : (
        <span className="text-muted-foreground">Not judged on v{ontologyVersion} yet</span>
      )}
    </div>
  )
}
