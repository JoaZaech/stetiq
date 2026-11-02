import type { EvaluationResult } from '@/api/ontology-versions'
import { formatFraction, formatMetric, formatPercent } from '@/lib/format'
import { evaluatorLabel } from './evaluator-metrics'

/** One headline metric of a built-in Evaluator, as its card shows it. */
interface HeadlineSpec {
  /** The wire metric name; never renamed (`docs/architecture.md` › *Reserved Evaluator names*). */
  metric: string
  label: string
  /** A ratio (0 to 1), shown as a percentage. */
  percent?: boolean
  /** The metric this one is a count out of, shown as "a / b". */
  of?: string
}

/** How a built-in Evaluator reads on its card: a title, a one-sentence tooltip, its headline metrics. */
interface EvaluatorDisplay {
  title: string
  tooltip: string
  headlines: readonly HeadlineSpec[]
}

/**
 * Display labels for the built-in Evaluators (`RESERVED_EVALUATOR_NAMES`), Ontology
 * Version and Construction Run ones alike. Only the labels are the UI's: the keys and
 * metric names are what users' Gates name, so they stay as the server sends them.
 */
export const EVALUATOR_DISPLAY: Readonly<Record<string, EvaluatorDisplay>> = {
  structural_answerability: {
    title: 'Answerable questions',
    tooltip: 'Competency Questions whose Concepts this Ontology has, out of all the Use Case’s questions.',
    headlines: [
      { metric: 'answerable_questions', label: 'Answerable', of: 'questions' },
      { metric: 'unanswerable_questions', label: 'Unanswerable' },
    ],
  },
  competency_question_coverage: {
    title: 'Concepts traced to a question',
    tooltip: 'The share of Concepts that at least one Competency Question references.',
    headlines: [{ metric: 'traced_concept_ratio', label: 'Traced', percent: true }],
  },
  unjustified_additions: {
    title: 'Unjustified additions',
    tooltip: 'Concepts the evolving run behind this Candidate added that no Competency Question needs.',
    headlines: [{ metric: 'unjustified_additions', label: 'Unjustified', of: 'added_concepts' }],
  },
  definitions: {
    title: 'Concepts with a Definition',
    tooltip: 'The share of Classes, Relations, Attributes and Vocabulary Values that have a Definition.',
    headlines: [{ metric: 'definition_ratio', label: 'Defined', percent: true }],
  },
  constraint_consistency: {
    title: 'Axiom consistency',
    tooltip: 'Constraints and deprecations that validation allows but that contradict each other.',
    headlines: [{ metric: 'inconsistencies', label: 'Inconsistencies' }],
  },
  orphan_concepts: {
    title: 'Orphan Concepts',
    tooltip: 'Classes and Relations that no pattern uses.',
    headlines: [{ metric: 'orphan_concepts', label: 'Orphans' }],
  },
  isolated_node_types: {
    title: 'Isolated Classes',
    tooltip: 'Classes that no Relation connects to any other Class.',
    headlines: [{ metric: 'isolated_node_types', label: 'Isolated' }],
  },
  redundancy: {
    title: 'Redundancy',
    tooltip: 'Structure stated more than once, such as two Classes with the same Attributes.',
    headlines: [{ metric: 'duplicate_structure_concepts', label: 'Duplicate structures' }],
  },
  hierarchy: {
    title: 'Class hierarchy',
    tooltip: 'The shape of the Class hierarchy: how deep it goes and how many Classes have no parent.',
    headlines: [
      { metric: 'max_depth', label: 'Max depth' },
      { metric: 'root_node_types', label: 'Root Classes' },
    ],
  },
  conformance: {
    title: 'Conformance',
    tooltip: 'How closely the graph the run built matches the Ontology Version it declared.',
    headlines: [
      { metric: 'score', label: 'Score', percent: true },
      { metric: 'mismatches', label: 'Mismatches' },
    ],
  },
  observed_schema: {
    title: 'Observed graph',
    tooltip: 'What the run’s graph holds: instances of Classes and of Relations.',
    headlines: [
      { metric: 'nodes', label: 'Instances of Classes' },
      { metric: 'relationships', label: 'Instances of Relations' },
    ],
  },
  competency_question_execution: {
    title: 'Questions executed',
    tooltip: 'Competency Questions with a query, executed against the graph: how many returned what they should.',
    headlines: [
      { metric: 'passed_questions', label: 'Passed', of: 'questions' },
      { metric: 'failed_questions', label: 'Failed' },
    ],
  },
}

/** A metric as a card shows it: a readable label and a formatted value. */
export interface Headline {
  /** The wire metric name, for the "Show all metrics" table and tests. */
  metric: string
  label: string
  value: string
}

/** One Evaluator result as a card: what its title, tooltip and headline metrics read. */
export interface EvaluatorCard {
  /** The Evaluator's name as configured, e.g. `coverage (min=1)`: unique per card, as in the raw table. */
  evaluator: string
  title: string
  /** One sentence on what it measures; null for an Evaluator outside the map. */
  tooltip: string | null
  headlines: Headline[]
  useCaseVersion: number | null
}

function headline(spec: HeadlineSpec, metrics: Readonly<Record<string, number>>): Headline | null {
  const value = metrics[spec.metric]
  if (value === undefined) return null
  const total = spec.of === undefined ? undefined : metrics[spec.of]
  const formatted =
    total !== undefined ? formatFraction(value, total) : spec.percent ? formatPercent(value) : formatMetric(value)
  return { metric: spec.metric, label: spec.label, value: formatted }
}

/** An Evaluator outside the map, or one missing its headlines: its first metric, under its raw name. */
function firstMetric(metrics: Readonly<Record<string, number>>): Headline[] {
  const first = Object.entries(metrics)[0]
  return first ? [{ metric: first[0], label: first[0], value: formatMetric(first[1]) }] : []
}

/**
 * A result's card: a built-in Evaluator's title, tooltip and headline metrics from
 * `EVALUATOR_DISPLAY`; any other Evaluator, such as a user's own, titled by its raw
 * name with its first metric. Parameters are kept in the title, so two configurations
 * of one Evaluator stay apart.
 */
export function evaluatorCard(result: EvaluationResult): EvaluatorCard {
  const evaluator = evaluatorLabel(result.evaluator, result.parameters)
  const display = Object.hasOwn(EVALUATOR_DISPLAY, result.evaluator) ? EVALUATOR_DISPLAY[result.evaluator] : undefined
  const headlines = display?.headlines.flatMap((spec) => headline(spec, result.metrics) ?? []) ?? []
  const params = evaluator.slice(result.evaluator.length)
  return {
    evaluator,
    title: display ? display.title + params : evaluator,
    tooltip: display?.tooltip ?? null,
    headlines: headlines.length > 0 ? headlines : firstMetric(result.metrics),
    useCaseVersion: result.use_case_version,
  }
}

/** One card per result: the built-in Evaluators in the map's order, then the others by name. */
export function evaluatorCards(results: readonly EvaluationResult[]): EvaluatorCard[] {
  const order = Object.keys(EVALUATOR_DISPLAY)
  const rank = (r: EvaluationResult) => {
    const i = order.indexOf(r.evaluator)
    return i === -1 ? order.length : i
  }
  return results
    .map((result) => ({ rank: rank(result), card: evaluatorCard(result) }))
    .sort((a, b) => a.rank - b.rank || a.card.evaluator.localeCompare(b.card.evaluator))
    .map(({ card }) => card)
}
