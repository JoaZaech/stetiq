"""The Evaluator plug-in interface.

An Evaluator is a pluggable measurement producing named metrics and optional
per-item details. There are two subject kinds:

- `"ontology_version"`: `OntologyVersionEvaluator.evaluate(version)` gets the
  `OntologyVersion` only, with no Graph Source access. Pure function of the Ontology.
- `"construction_run"`: `ConstructionRunEvaluator.evaluate(run)` gets a
  `ConstructionRunSubject`: the run, its Declared Ontology, its Observed Schema
  and read-only Graph Source access. Invoked at the end of a run (ticket #13).

Write a custom Evaluator by subclassing one of the two base classes, set a
unique `name`, and register it with `Client.register_evaluator`.
"""

from __future__ import annotations

import math
from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, ClassVar, Literal, Protocol

from stetiq.errors import EvaluatorError

if TYPE_CHECKING:
    from stetiq.tracking.entities import OntologyVersion

SubjectKind = Literal["ontology_version", "construction_run"]
MetricValue = int | float


@dataclass(frozen=True)
class Detail:
    """One per-item finding, e.g. the Concept that made a metric non-zero.

    `item` names the thing (a Concept label, a pattern, a Competency Question id);
    `metric` optionally names the metric it contributes to.
    """

    item: str
    message: str = ""
    metric: str | None = None


@dataclass(frozen=True)
class Evaluation:
    """What an Evaluator returns: named metrics plus optional details."""

    metrics: Mapping[str, MetricValue]
    details: Sequence[Detail] = field(default=())


class OntologyVersionEvaluator(ABC):
    """Scores an Ontology Version. Has no Graph Source access."""

    subject_kind: ClassVar[SubjectKind] = "ontology_version"
    name: str

    @abstractmethod
    def evaluate(self, version: OntologyVersion) -> Evaluation: ...


class ReadOnlyGraphSource(Protocol):
    """Read-only access to a Construction Run's Graph Source.

    Defined by the Graph Source adapter (ticket #4/#7); evaluators must never write.
    """


class ConstructionRunSubject(Protocol):
    """What a run-level Evaluator sees. Concrete type supplied by ticket #13."""

    @property
    def knowledge_graph(self) -> str: ...

    @property
    def run_id(self) -> str: ...

    @property
    def declared_ontology(self) -> OntologyVersion: ...

    @property
    def observed_schema(self) -> Any: ...

    @property
    def graph_source(self) -> ReadOnlyGraphSource: ...


class ConstructionRunEvaluator(ABC):
    """Scores a Construction Run: gets the Observed Schema and read-only Graph Source access."""

    subject_kind: ClassVar[SubjectKind] = "construction_run"
    name: str

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
    return Evaluation(dict(evaluation.metrics), tuple(evaluation.details))
