"""The run context: what an extraction pipeline gets from stetiq before it extracts.

`Client.run_context` composes it from existing service calls; `stetiq context` prints
`RunContext.to_dict()` as JSON for pipelines that don't use the Python SDK. It holds
Ontology, Use Case, metrics and counts only, never instance data (ADR 0001).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from stetiq import use_case as use_case_format
from stetiq.evaluation.run import CQ_EXECUTION_EVALUATOR
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
    - `evaluation_results`: the latest result of every Evaluator for that version.
    - `run`: the latest finished Construction Run standing for that version (None when
      there is none), and `run_evaluation_results` its run-level results, including
      `competency_question_execution`."""

    knowledge_graph: str
    ontology_version: OntologyVersion
    use_case_version: UseCaseVersion | None
    evaluation_results: tuple[EvaluationResult, ...]
    run: ConstructionRun | None = None
    run_evaluation_results: tuple[EvaluationResult, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        """A stable, JSON-ready shape (see the guide's "The run context")."""
        use_case = None if self.use_case_version is None else self.use_case_version.use_case
        return {
            "knowledge_graph": self.knowledge_graph,
            "ontology_version": {
                "number": self.ontology_version.number,
                "ontology": codec.ontology_to_json(self.ontology_version.ontology),
            },
            "use_case_version": None
            if self.use_case_version is None or use_case is None
            else {
                "number": self.use_case_version.number,
                "use_case": use_case_format.to_dict(use_case),
            },
            "competency_questions": self._questions(),
            "evaluation_results": [
                codec.evaluation_result_to_json(r) for r in self.evaluation_results
            ],
            "run": None
            if self.run is None
            else {
                "id": self.run.id,
                "evaluation_results": [
                    codec.evaluation_result_to_json(r) for r in self.run_evaluation_results
                ],
            },
        }

    def _questions(self) -> list[dict[str, Any]]:
        """Each Competency Question with the (Consumer, Task) pairs it serves and its
        executed result on `run` (`{status, rows}`; None when it was not executed)."""
        if self.use_case_version is None:
            return []
        use_case = self.use_case_version.use_case
        executed = self._executed()
        return [
            {
                "id": q.id,
                "question": q.question,
                "serves": [
                    {"consumer": c.id, "task": t.id}
                    for c in use_case.consumers
                    for t in c.tasks
                    if q.id in t.competency_questions
                ],
                "execution": executed.get(q.id),
            }
            for q in use_case.competency_questions
        ]

    def _executed(self) -> dict[str, dict[str, Any]]:
        execution = next(
            (
                r
                for r in self.run_evaluation_results
                if r.evaluator == CQ_EXECUTION_EVALUATOR and not r.parameters
            ),
            None,
        )
        if execution is None:
            return {}
        return {
            d.item: {"status": d.data["status"], "rows": d.data["rows"]}
            for d in execution.details
            if d.data is not None and "status" in d.data
        }
