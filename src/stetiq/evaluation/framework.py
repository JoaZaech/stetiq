"""The Evaluator plug-in interface.

An Evaluator is a pluggable measurement producing named metrics and optional
per-item details. There are two subject kinds:

- `"ontology_version"`: `OntologyVersionEvaluator.evaluate(version)` gets the
  `OntologyVersion` only, with no Graph Source access. Pure function of the Ontology.
- `"construction_run"`: `ConstructionRunEvaluator.evaluate(run)` gets a
  `ConstructionRunSubject`: the run, its Declared Ontology, its Observation
  (Observed Schema) and read-only Graph Source access. Invoked at the end of a
  run (ticket #13).

Write a custom Evaluator by subclassing one of the two base classes, set a
unique `name`, and register it with `Client.register_evaluator`.
"""

from __future__ import annotations

import json
import math
from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, ClassVar, Literal, Protocol

from stetiq.errors import EvaluatorError

if TYPE_CHECKING:
    from stetiq.tracking.entities import ConstructionRun, Observation, OntologyVersion

SubjectKind = Literal["ontology_version", "construction_run"]
MetricValue = int | float
# An Evaluator's configuration, e.g. which gold Ontology Version it compares against.
ParameterValue = str | int | float


@dataclass(frozen=True)
class Detail:
    """One per-item finding, e.g. the Concept that made a metric non-zero.

    `item` names the thing (a Concept label, a pattern, a Competency Question id);
    `metric` optionally names the metric it contributes to; `data` optionally carries
    structured, JSON-serialisable facts about the item (e.g. a Competency Question's
    required and missing Concepts) for Gates and tools to read.
    """

    item: str
    message: str = ""
    metric: str | None = None
    data: Mapping[str, Any] | None = None


@dataclass(frozen=True)
class Evaluation:
    """What an Evaluator returns: named metrics plus optional details."""

    metrics: Mapping[str, MetricValue]
    details: Sequence[Detail] = field(default=())


class OntologyVersionEvaluator(ABC):
    """Scores an Ontology Version. Has no Graph Source access."""

    subject_kind: ClassVar[SubjectKind] = "ontology_version"
    name: str

    @property
    def parameters(self) -> Mapping[str, ParameterValue]:
        """Configuration this instance runs with; stored with its result.

        Results are kept per (name, parameters): evaluating with different
        parameters (e.g. another reference Ontology) adds a separate result.
        """
        return {}

    @abstractmethod
    def evaluate(self, version: OntologyVersion) -> Evaluation: ...


class ReadOnlyGraphSource(Protocol):
    """A Graph Source narrowed to the run's scope, read-only (executed Competency Questions).

    Ticket #13 binds `GraphSource.execute_read(scope, ...)` to the run's Observation
    scope. Results are evaluated and discarded, never stored (ADR 0001).
    """

    def execute_read(
        self, query: str, parameters: Mapping[str, Any] | None = None
    ) -> list[dict[str, Any]]: ...


class ConstructionRunSubject(Protocol):
    """What a run-level Evaluator sees; the concrete value is built by ticket #13.

    Results are stored with subject_kind "construction_run", subject_id `run.id`.
    """

    @property
    def run(self) -> ConstructionRun: ...

    @property
    def declared_ontology(self) -> OntologyVersion:
        """The Ontology Version the run consumed (`run.ontology_version`)."""
        ...

    @property
    def observation(self) -> Observation:
        """The Observation made at the end of the run; `.schema` is the Observed Schema."""
        ...

    @property
    def graph_source(self) -> ReadOnlyGraphSource: ...


class ConstructionRunEvaluator(ABC):
    """Scores a Construction Run: gets the Observed Schema and read-only Graph Source access."""

    subject_kind: ClassVar[SubjectKind] = "construction_run"
    name: str

    @property
    def parameters(self) -> Mapping[str, ParameterValue]:
        """Configuration this instance runs with; stored with its result."""
        return {}

    @abstractmethod
    def evaluate(self, run: ConstructionRunSubject) -> Evaluation: ...


Evaluator = OntologyVersionEvaluator | ConstructionRunEvaluator


def check_evaluator(evaluator: Any) -> None:
    if not isinstance(evaluator, (OntologyVersionEvaluator, ConstructionRunEvaluator)):
        raise EvaluatorError(
            f"{evaluator!r} is not an Evaluator; subclass OntologyVersionEvaluator "
            "or ConstructionRunEvaluator"
        )
    name = getattr(evaluator, "name", None)
    if not isinstance(name, str) or not name.strip():
        raise EvaluatorError(f"{type(evaluator).__name__} needs a non-empty string `name`")


def check_evaluation(evaluator_name: str, evaluation: Any) -> Evaluation:
    """Validate what an Evaluator returned; raise EvaluatorError naming the Evaluator."""
    if not isinstance(evaluation, Evaluation):
        raise EvaluatorError(
            f"Evaluator {evaluator_name!r} returned {evaluation!r}, expected an Evaluation"
        )
    for metric, value in evaluation.metrics.items():
        if not isinstance(metric, str) or not metric:
            raise EvaluatorError(f"Evaluator {evaluator_name!r}: metric names must be strings")
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
        ):
            raise EvaluatorError(
                f"Evaluator {evaluator_name!r}: metric {metric!r} must be a finite number, "
                f"got {value!r}"
            )
    for detail in evaluation.details:
        if not isinstance(detail, Detail):
            raise EvaluatorError(
                f"Evaluator {evaluator_name!r}: details must be Detail values, got {detail!r}"
            )
        if detail.data is not None:
            try:
                if not isinstance(detail.data, Mapping):
                    raise TypeError
                json.dumps(detail.data, allow_nan=False)
            except (TypeError, ValueError):
                raise EvaluatorError(
                    f"Evaluator {evaluator_name!r}: detail {detail.item!r} data must be a "
                    "JSON-serialisable mapping"
                ) from None
    return Evaluation(dict(evaluation.metrics), tuple(evaluation.details))


def check_parameters(evaluator_name: str, parameters: Any) -> dict[str, ParameterValue]:
    """Validate an Evaluator's parameters: string keys, str/int/float (finite) values."""
    if not isinstance(parameters, Mapping):
        raise EvaluatorError(f"Evaluator {evaluator_name!r}: parameters must be a mapping")
    for key, value in parameters.items():
        if not isinstance(key, str) or not key:
            raise EvaluatorError(f"Evaluator {evaluator_name!r}: parameter names must be strings")
        if isinstance(value, bool) or not isinstance(value, (str, int, float)) or (
            isinstance(value, float) and not math.isfinite(value)
        ):
            raise EvaluatorError(
                f"Evaluator {evaluator_name!r}: parameter {key!r} must be a string or "
                f"finite number, got {value!r}"
            )
    return dict(parameters)
