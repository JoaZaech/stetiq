"""The run context: what the upstream pipeline gets from stetiq before it extracts.

`Client.run_context` composes it from existing service calls; `stetiq context` prints
`RunContext.to_dict()` as JSON for upstream pipelines that don't use the Python SDK. It
holds Ontology, Use Case, metrics and counts only, never instance data (ADR 0001):
evaluation results come without their details, which can quote observed values.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from stetiq import use_case as use_case_format
from stetiq.evaluation.run import QuestionExecution
from stetiq.tracking import codec
from stetiq.tracking.entities import (
    ConstructionRun,
    EvaluationResult,
    OntologyVersion,
    UseCaseVersion,
)


@dataclass(frozen=True)
class RunContext:
    """- `ontology_version`: the version to extract against, as a suggestion.
    - `use_case_version`: the latest Use Case Version (None without a Use Case).
    - `evaluation_results`: the latest result of every Evaluator for that version,
      metrics only (`details` is always empty).
    - `run`: the latest finished Construction Run standing for that version (None when
      there is none), `run_evaluation_results` its run-level results (metrics only), and
      `question_executions` each executed Competency Question's status and row count on
      it."""

    knowledge_graph: str
    ontology_version: OntologyVersion
    use_case_version: UseCaseVersion | None
    evaluation_results: tuple[EvaluationResult, ...]
    run: ConstructionRun | None = None
    run_evaluation_results: tuple[EvaluationResult, ...] = ()
    question_executions: Mapping[str, QuestionExecution] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """A stable, JSON-ready shape (see the guide's "The run context")."""
        return {
            "knowledge_graph": self.knowledge_graph,
            "ontology_version": {
                "number": self.ontology_version.number,
                "ontology": codec.ontology_to_json(self.ontology_version.ontology),
            },
            "use_case_version": None
            if self.use_case_version is None
            else {
                "number": self.use_case_version.number,
                "use_case": use_case_format.to_dict(self.use_case_version.use_case),
            },
            "competency_questions": self._questions(),
            "evaluation_results": [_metrics_only(r) for r in self.evaluation_results],
            "run": None
            if self.run is None
            else {
                "id": self.run.id,
                "evaluation_results": [_metrics_only(r) for r in self.run_evaluation_results],
            },
        }

    def _questions(self) -> list[dict[str, Any]]:
        """Each Competency Question with the (Consumer, Task) pairs it serves and its
        executed result on `run` (`{status, rows}`; None when it was not executed)."""
        if self.use_case_version is None:
            return []
        use_case = self.use_case_version.use_case
        questions = []
        for q in use_case.competency_questions:
            executed = self.question_executions.get(q.id)
            questions.append(
                {
                    "id": q.id,
                    "question": q.question,
                    "serves": [{"consumer": c.id, "task": t.id} for c, t in use_case.serving(q.id)],
                    "execution": None
                    if executed is None
                    else {"status": executed.status, "rows": executed.rows},
                }
            )
        return questions


def _metrics_only(result: EvaluationResult) -> dict[str, Any]:
    return {
        "evaluator": result.evaluator,
        "parameters": dict(result.parameters),
        "metrics": dict(result.metrics),
        "use_case_version": result.use_case_version,
    }
