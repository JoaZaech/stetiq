"""The run context: what the upstream pipeline gets from stetiq before it extracts.

`Client.run_context` composes it from existing service calls; `stetiq context` prints
`RunContext.to_dict()` as JSON for upstream pipelines that don't use the Python SDK. It
holds Ontology, Use Case, metrics and counts, never instance data (ADR 0001): only the
built-ins that judge an Ontology Version keep their details (ADR 0010); every other
result comes without them, since they can quote observed values (`Client.run_context`
drops them; `to_dict` writes the results in their wire form).
"""

from __future__ import annotations

import dataclasses
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from stetiq import use_case as use_case_format
from stetiq.evaluation.run import QuestionExecution
from stetiq.gates import ConformanceGate, MetricGate
from stetiq.ontology.diff import OntologyDiff
from stetiq.tracking import codec, wire
from stetiq.tracking.entities import (
    ConstructionRun,
    ConsumerGateResult,
    EvaluationResult,
    GateResult,
    OntologyVersion,
    UseCaseVersion,
)

NOT_EVALUATED: dict[str, Any] = {"status": "not_evaluated"}


@dataclass(frozen=True)
class RecordedVerdicts:
    """The verdicts CI recorded about one Construction Run, read and never computed
    (ADR 0007): `Client._recorded_verdicts` reads them for any run.

    - `gate_result`: the latest Gate result about the run, else about its Ontology
      Version (None: not evaluated).
    - `consumer_gate_results`: each Consumer declaring a Consumer Gate, in Use Case
      order, with its latest Consumer Gate result about the run (None: not evaluated).
    """

    gate_result: GateResult | None = None
    consumer_gate_results: Mapping[str, ConsumerGateResult | None] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """`gate_result` and `consumer_gate_results`, each verdict with a `status` of
        `passed` or `failed`, or `{"status": "not_evaluated"}` when none was recorded."""
        return {
            "gate_result": NOT_EVALUATED
            if self.gate_result is None
            else _gate_result_to_dict(self.gate_result),
            "consumer_gate_results": [
                {"consumer": consumer, **NOT_EVALUATED}
                if result is None
                else {
                    "status": _status(result.passed),
                    **codec.consumer_gate_result_to_json(result),
                }
                for consumer, result in self.consumer_gate_results.items()
            ],
        }


_QUOTING_CHECKS = frozenset({MetricGate.check, ConformanceGate.check})


def without_quoted_reasons(result: GateResult) -> GateResult:
    """`result` with only the reasons stetiq writes itself. A `metric` or `conformance`
    Gate's first reason states the observed value against its limit; the rest list the
    Evaluator's details or Conformance mismatches, which can quote values observed in the
    graph, so they are dropped (ADR 0001, ADR 0010). Other Gates' reasons name only
    Concepts and type counts."""
    return dataclasses.replace(
        result,
        outcomes=tuple(
            dataclasses.replace(o, reasons=o.reasons[:1]) if o.gate.check in _QUOTING_CHECKS else o
            for o in result.outcomes
        ),
    )


def _status(passed: bool) -> str:
    return "passed" if passed else "failed"


def _gate_result_to_dict(result: GateResult) -> dict[str, Any]:
    return {"status": _status(result.passed), **codec.gate_result_to_json(result)}


@dataclass(frozen=True)
class LastAttempt:
    """The latest ended Construction Run that consumed the Run Context's version
    (`TrackingService.latest_ended_run`), whether or not its Candidate was promoted.

    - `run`: the run, `finished` or `failed` by strict Evolution Mode.
    - `added`: the Ontology Diff from the version it consumed to its Candidate, or to the
      Candidate it would have produced (strict); empty when it added nothing.
    - `evaluation_results`: its run-level results (metrics only), `question_executions`
      each executed Competency Question's status and row count, and `verdicts` the
      recorded Gate and Consumer Gate verdicts about it."""

    run: ConstructionRun
    added: OntologyDiff
    evaluation_results: tuple[EvaluationResult, ...] = ()
    question_executions: Mapping[str, QuestionExecution] = field(default_factory=dict)
    verdicts: RecordedVerdicts = field(default_factory=RecordedVerdicts)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.run.id,
            "status": self.run.status,
            "ontology_version": self.run.ontology_version,
            "candidate_version": self.run.candidate_version,
            "added": wire.ontology_diff_to_json(self.added),
            "evaluation_results": [
                codec.evaluation_result_to_json(r) for r in self.evaluation_results
            ],
            "competency_questions": [
                {"id": question, "status": e.status, "rows": e.rows}
                for question, e in self.question_executions.items()
            ],
            **self.verdicts.to_dict(),
        }


@dataclass(frozen=True)
class RunContext:
    """- `ontology_version`: the version to extract against, as a suggestion.
    - `use_case_version`: the latest Use Case Version (None without a Use Case).
    - `evaluation_results`: the latest result of every Evaluator for that version, with
      `details` only for the built-ins in `RUN_CONTEXT_DETAIL_EVALUATORS`.
    - `run`: the latest finished Construction Run standing for that version (None when
      there is none), `run_evaluation_results` its run-level results (metrics only), and
      `question_executions` each executed Competency Question's status and row count on
      it.
    - `verdicts`: the recorded Gate and Consumer Gate verdicts about `run` (the Gate
      result falls back to the Ontology Version's).
    - `last_attempt`: the latest ended run that consumed the version, with what it added
      and how it was judged (None when no run has ended against it)."""

    knowledge_graph: str
    ontology_version: OntologyVersion
    use_case_version: UseCaseVersion | None
    evaluation_results: tuple[EvaluationResult, ...]
    run: ConstructionRun | None = None
    run_evaluation_results: tuple[EvaluationResult, ...] = ()
    question_executions: Mapping[str, QuestionExecution] = field(default_factory=dict)
    verdicts: RecordedVerdicts = field(default_factory=RecordedVerdicts)
    last_attempt: LastAttempt | None = None

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
            **self.verdicts.to_dict(),
            "last_attempt": None if self.last_attempt is None else self.last_attempt.to_dict(),
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
