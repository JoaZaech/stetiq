"""Run-level evaluation: Evaluators whose subject is a Construction Run.

Built-in run Evaluators, by stable name (Gates refer to these names and metrics):

- `conformance` (`RUN_CONFORMANCE_EVALUATOR`, server-side): the run's Conformance as
  metrics. Metrics `score`, `mismatches`, `declared_absent`, `undeclared`,
  `pattern_mismatches`, `property_mismatches`; one Detail per mismatch.
- `observed_schema` (`OBSERVED_SCHEMA_EVALUATOR`, server-side): Observed Schema
  statistics (aggregates only).
- `competency_question_execution` (`CQ_EXECUTION_EVALUATOR`, SDK-side, because the
  Graph Source adapter lives in the user's process): executes every Competency
  Question that has a query, read-only. Returned rows are judged and discarded,
  never stored (ADR 0001).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from stetiq.conformance import assess_conformance
from stetiq.evaluation.framework import (
    ConstructionRunEvaluator,
    ConstructionRunSubject,
    Detail,
    Evaluation,
    ReadOnlyGraphSource,
)
from stetiq.use_case import CompetencyQuestion, UseCase

if TYPE_CHECKING:
    from stetiq.graph_source import GraphSource, GraphSourceScope
    from stetiq.tracking.entities import ConstructionRun, Observation, OntologyVersion

RUN_CONFORMANCE_EVALUATOR = "conformance"
OBSERVED_SCHEMA_EVALUATOR = "observed_schema"
CQ_EXECUTION_EVALUATOR = "competency_question_execution"


@dataclass(frozen=True)
class ScopedGraphSource:
    """A Graph Source bound to one scope, exposing only the read call."""

    source: GraphSource
    scope: GraphSourceScope

    def execute_read(
        self, query: str, parameters: Mapping[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        return self.source.execute_read(self.scope, query, parameters)


class NoGraphSource:
    """For run Evaluators that run in the tracking service, which never reaches the graph."""

    def execute_read(self, query: str, parameters: Mapping[str, Any] | None = None):
        raise RuntimeError("The tracking service has no Graph Source access")


@dataclass(frozen=True)
class RunSubject:
    """The concrete `ConstructionRunSubject`."""

    run: ConstructionRun
    declared_ontology: OntologyVersion
    observation: Observation
    graph_source: ReadOnlyGraphSource


class RunConformance(ConstructionRunEvaluator):
    name = RUN_CONFORMANCE_EVALUATOR

    def evaluate(self, run: ConstructionRunSubject) -> Evaluation:
        conformance = assess_conformance(run.declared_ontology.ontology, run.observation.schema)
        groups = {
            "declared_absent": conformance.declared_absent,
            "undeclared": conformance.undeclared,
            "pattern_mismatches": conformance.pattern_mismatches,
            "property_mismatches": conformance.property_mismatches,
        }
        details = [
            Detail(
                item=m.subject,
                message=m.detail or str(m.kind),
                metric=metric,
                data={"subject_kind": m.subject_kind, "kind": str(m.kind)},
            )
            for metric, mismatches in groups.items()
            for m in mismatches
        ]
        return Evaluation(
            metrics={
                "score": conformance.score,
                "mismatches": len(conformance.mismatches),
                **{metric: len(ms) for metric, ms in groups.items()},
            },
            details=details,
        )


class ObservedSchemaStatistics(ConstructionRunEvaluator):
    """The Observed Schema's aggregate statistics as metrics.

    `nodes` sums the per-label node counts (a node with two labels counts twice, as in
    the Observed Schema); `properties` counts (owner, property) pairs over node and
    relationship types; `mean_fill_rate` averages their fill rates (1.0 when none).
    Details: one per node type, relationship type (`data` = count, fill rates) and
    pattern (`data` = count, out/in degree)."""

    name = OBSERVED_SCHEMA_EVALUATOR

    def evaluate(self, run: ConstructionRunSubject) -> Evaluation:
        schema = run.observation.schema
        types = (*schema.node_types, *schema.relationship_types)
        fill_rates = [p.fill_rate for t in types for p in t.properties]
        details = [
            Detail(
                item=t.label,
                message=f"{t.count} observed",
                data={"count": t.count, "fill_rates": {p.name: p.fill_rate for p in t.properties}},
            )
            for t in types
        ] + [
            Detail(
                item=str(p.pattern),
                message=f"{p.count} observed",
                data={
                    "count": p.count,
                    "out_degree": p.out_degree.to_dict(),
                    "in_degree": p.in_degree.to_dict(),
                },
            )
            for p in schema.patterns
        ]
        return Evaluation(
            metrics={
                "node_types": len(schema.node_types),
                "relationship_types": len(schema.relationship_types),
                "patterns": len(schema.patterns),
                "nodes": sum(n.count for n in schema.node_types),
                "relationships": sum(r.count for r in schema.relationship_types),
                "properties": len(fill_rates),
                "mean_fill_rate": sum(fill_rates) / len(fill_rates) if fill_rates else 1.0,
            },
            details=details,
        )


class CompetencyQuestionExecution(ConstructionRunEvaluator):
    """Executes every Competency Question that has a query through the run's read-only
    Graph Source and judges the result. Runs in the SDK process.

    A question passes when its result is non-empty (no `expected_answer`) or matches
    its `expected_answer` (see `matches_expected_answer`). A query that raises fails
    the question with status "error". Rows are judged here and dropped: only the row
    count and the verdict are kept (ADR 0001).

    Metrics: `questions` (executed), `passed_questions`, `failed_questions` (errors
    included), `skipped_questions` (no query, not executed), `pass_ratio` (1.0 when
    none executed). One Detail per executed question: `item` = id, `metric` =
    `passed_questions` / `failed_questions`, `data` = {status: passed|failed|error,
    rows: count, check: non_empty|expected_answer, error?: exception type}.
    """

    name = CQ_EXECUTION_EVALUATOR

    def __init__(self, use_case: UseCase) -> None:
        self.use_case = use_case

    def evaluate(self, run: ConstructionRunSubject) -> Evaluation:
        questions = self.use_case.competency_questions
        executed = [(q, q.query) for q in questions if q.query]
        details = [self._execute(q, query, run.graph_source) for q, query in executed]
        passed = sum(d.data is not None and d.data["status"] == "passed" for d in details)
        return Evaluation(
            metrics={
                "questions": len(executed),
                "passed_questions": passed,
                "failed_questions": len(executed) - passed,
                "skipped_questions": len(questions) - len(executed),
                "pass_ratio": passed / len(executed) if executed else 1.0,
            },
            details=details,
        )

    @staticmethod
    def _execute(question: CompetencyQuestion, query: str, graph: ReadOnlyGraphSource) -> Detail:
        check = "non_empty" if question.expected_answer is None else "expected_answer"
        try:
            rows = graph.execute_read(query)
        except Exception as exc:  # noqa: BLE001 - any failure fails the question
            # Only the exception type: a database message can quote instance values.
            return Detail(
                item=question.id,
                message=f"query failed: {type(exc).__name__}",
                metric="failed_questions",
                data={"status": "error", "rows": 0, "check": check, "error": type(exc).__name__},
            )
        if question.expected_answer is None:
            ok = len(rows) > 0
            message = "non-empty result" if ok else "empty result"
        else:
            ok = matches_expected_answer(rows, question.expected_answer)
            message = "matches the expected answer" if ok else "does not match the expected answer"
        status = "passed" if ok else "failed"
        return Detail(
            item=question.id,
            message=message,
            metric=f"{status}_questions",
            data={"status": status, "rows": len(rows), "check": check},
        )


def matches_expected_answer(rows: list[dict[str, Any]], expected: Any) -> bool:
    """Whether a query result matches a Competency Question's `expected_answer`.

    - a mapping: the result is exactly one row equal to it;
    - a list of mappings: the rows, in any order (as a multiset);
    - a list of anything else: the values of a single-column result, in any order;
    - anything else (a scalar): exactly one row with a single column equal to it.
    """
    if isinstance(expected, Mapping):
        return len(rows) == 1 and rows[0] == dict(expected)
    if isinstance(expected, list):
        if all(isinstance(e, Mapping) for e in expected) and expected:
            actual = rows
        else:
            if any(len(r) != 1 for r in rows):
                return False
            actual = [next(iter(r.values())) for r in rows]
        return _same_multiset(actual, list(expected))
    return len(rows) == 1 and len(rows[0]) == 1 and _equal(next(iter(rows[0].values())), expected)


def _equal(a: Any, b: Any) -> bool:
    # JSON true is not 1: keep booleans apart from numbers.
    return isinstance(a, bool) == isinstance(b, bool) and a == b


def _same_multiset(actual: list[Any], expected: list[Any]) -> bool:
    if len(actual) != len(expected):
        return False
    remaining = list(expected)
    for value in actual:
        index = next((i for i, e in enumerate(remaining) if _equal(value, e)), None)
        if index is None:
            return False
        del remaining[index]
    return True


# Run in the tracking service at the end of every run with an Observation.
SERVER_RUN_EVALUATORS: tuple[ConstructionRunEvaluator, ...] = (
    RunConformance(),
    ObservedSchemaStatistics(),
)
