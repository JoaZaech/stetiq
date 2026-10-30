"""The Gate engine: Gates from the repo config file, evaluated as a pure function.

`evaluate_gates(gates, inputs)` takes Gate definitions and the results available for
one subject (an Ontology Version or a Construction Run) and returns pass/fail with
reasons per Gate. It does no I/O: the tracking service gathers `GateInputs` from its
own stored results, evaluates, and records the outcome (clients only send the Gate
definitions, so a recorded outcome cannot be forged).

Config (`gates:` section of `stetiq.yaml`), one entry per Gate::

    gates:
      - name: no-breaking-changes          # optional, defaults to the check name
        check: ontology_diff               # vs the Contract Alias's version
        max_classification: deprecating
"""

from __future__ import annotations

import os
from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar

import yaml

from stetiq.conformance import Conformance
from stetiq.errors import GateConfigError
from stetiq.graph_source import ObservedSchema
from stetiq.ontology.diff import Classification, OntologyDiff

if TYPE_CHECKING:
    from stetiq.tracking.entities import EvaluationResult


@dataclass(frozen=True)
class GateInputs:
    """Everything a Gate may look at for one subject. None = not available."""

    ontology_version: int  # the version the subject stands for
    contract_version: int | None = None
    diff: OntologyDiff | None = None  # contract_version -> ontology_version
    conformance: Conformance | None = None
    evaluations: Sequence[EvaluationResult] = ()  # latest per Evaluator (and parameters)
    observed: ObservedSchema | None = None  # the subject's Observed Schema
    baseline: ObservedSchema | None = None  # the Observation before it
    # Run-level results (ticket #13: conformance, observed_schema,
    # competency_question_execution, custom run Evaluators) of the subject's run.
    run_evaluations: Sequence[EvaluationResult] = ()


@dataclass(frozen=True)
class GateOutcome:
    gate: Gate
    passed: bool
    reasons: tuple[str, ...] = ()


class Gate(ABC):
    """One rule. `check` names the kind in config; `to_dict()` is the definition as
    recorded with each Gate result (round-trips through `gate_from_dict`)."""

    check: ClassVar[str]
    name: str

    @abstractmethod
    def evaluate(self, inputs: GateInputs) -> GateOutcome: ...

    @abstractmethod
    def params(self) -> dict[str, Any]: ...

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "check": self.check, **self.params()}

    def _outcome(self, passed: bool, *reasons: str) -> GateOutcome:
        return GateOutcome(gate=self, passed=passed, reasons=tuple(reasons))


@dataclass(frozen=True)
class OntologyDiffGate(Gate):
    """No change in the Ontology Diff from the Contract Alias's version may be classed
    more severe than `max_classification`."""

    name: str
    max_classification: Classification
    check: ClassVar[str] = "ontology_diff"

    def params(self) -> dict[str, Any]:
        return {"max_classification": str(self.max_classification)}

    def evaluate(self, inputs: GateInputs) -> GateOutcome:
        if inputs.diff is None:
            return self._outcome(False, "No Contract Alias version to diff against")
        limit = self.max_classification.severity
        worse = [c for c in inputs.diff.changes if c.classification.severity > limit]
        if not worse:
            return self._outcome(True)
        against = f"v{inputs.contract_version} -> v{inputs.ontology_version}"
        return self._outcome(
            False,
            *(
                f"{c.classification} change ({against}): {c.kind} {c.concept}"
                + (f": {c.detail}" if c.detail else "")
                for c in worse
            ),
        )


MAX_LISTED_REASONS = 20  # per Gate; the rest are summarised in one line


def _capped(reasons: list[str]) -> list[str]:
    if len(reasons) <= MAX_LISTED_REASONS:
        return reasons
    return reasons[:MAX_LISTED_REASONS] + [f"... and {len(reasons) - MAX_LISTED_REASONS} more"]


@dataclass(frozen=True)
class ConformanceGate(Gate):
    """The subject's Conformance score must be at least `min_score` (0..1)."""

    name: str
    min_score: float
    check: ClassVar[str] = "conformance"

    def params(self) -> dict[str, Any]:
        return {"min_score": self.min_score}

    def evaluate(self, inputs: GateInputs) -> GateOutcome:
        c = inputs.conformance
        if c is None:
            return self._outcome(
                False,
                f"No Conformance for Ontology Version {inputs.ontology_version}: "
                "no finished Construction Run produced or consumed it",
            )
        if c.score >= self.min_score:
            return self._outcome(True, f"Conformance {c.score:.4f} >= {self.min_score}")
        return self._outcome(
            False,
            f"Conformance {c.score:.4f} < {self.min_score}",
            *_capped(
                [
                    f"{m.kind} {m.subject_kind} {m.subject}" + (f": {m.detail}" if m.detail else "")
                    for m in c.mismatches
                ]
            ),
        )


@dataclass(frozen=True)
class MetricGate(Gate):
    """A metric of the latest result of `evaluator` must lie within [`min`, `max`]
    (either bound optional, at least one given). `parameters` picks one result when the
    Evaluator ran with several configurations (e.g. gold references).

    The result is the version's, else (for an Evaluator with no version result) the
    subject run's run-level result, e.g. `competency_question_execution`."""

    name: str
    evaluator: str
    metric: str
    min: float | None = None
    max: float | None = None
    parameters: Mapping[str, Any] | None = None
    check: ClassVar[str] = "metric"

    def params(self) -> dict[str, Any]:
        d: dict[str, Any] = {"evaluator": self.evaluator, "metric": self.metric}
        if self.min is not None:
            d["min"] = self.min
        if self.max is not None:
            d["max"] = self.max
        if self.parameters is not None:
            d["parameters"] = dict(self.parameters)
        return d

    def evaluate(self, inputs: GateInputs) -> GateOutcome:
        def matching(candidates: Sequence[EvaluationResult]) -> list[EvaluationResult]:
            return [
                r
                for r in candidates
                if r.evaluator == self.evaluator
                and (self.parameters is None or dict(r.parameters) == dict(self.parameters))
            ]

        results = matching(inputs.evaluations) or matching(inputs.run_evaluations)
        if not results:
            return self._outcome(
                False,
                f"No result of Evaluator {self.evaluator!r} for Ontology Version "
                f"{inputs.ontology_version} or its run" + (f" with parameters {dict(self.parameters)}" if self.parameters else ""),
            )
        if len(results) > 1:
            return self._outcome(
                False,
                f"Evaluator {self.evaluator!r} has {len(results)} results with different "
                "parameters; set 'parameters' on the Gate to pick one: "
                + "; ".join(str(r.parameters) for r in results),
            )
        [result] = results
        key = f"{self.evaluator}.{self.metric}"
        if self.metric not in result.metrics:
            return self._outcome(
                False,
                f"Evaluator {self.evaluator!r} reports no metric {self.metric!r} "
                f"(has: {', '.join(sorted(result.metrics)) or 'none'})",
            )
        value = result.metrics[self.metric]
        violations = []
        if self.min is not None and value < self.min:
            violations.append(f"{key} = {value:g} < min {self.min:g}")
        if self.max is not None and value > self.max:
            violations.append(f"{key} = {value:g} > max {self.max:g}")
        if not violations:
            return self._outcome(True, f"{key} = {value:g}")
        details = [
            f"{d.item}: {d.message}" if d.message else d.item
            for d in result.details
            if d.metric in (None, self.metric)
        ]
        return self._outcome(False, *violations, *_capped(details))


@dataclass(frozen=True)
class CountDropGate(Gate):
    """No node or relationship type's count in the Observed Schema may drop by more
    than `max_drop` (a fraction, 0.1 = 10%) from the Observation before it. A type that
    disappears dropped 100%; new types are ignored."""

    name: str
    max_drop: float
    check: ClassVar[str] = "count_drop"

    def params(self) -> dict[str, Any]:
        return {"max_drop": self.max_drop}

    def evaluate(self, inputs: GateInputs) -> GateOutcome:
        if inputs.observed is None:
            return self._outcome(
                False,
                f"No Observation for Ontology Version {inputs.ontology_version}: "
                "no finished Construction Run produced or consumed it",
            )
        if inputs.baseline is None:
            return self._outcome(True, "No earlier Observation to compare type counts with")
        drops = []
        for kind, before, after in (
            ("node type", inputs.baseline.node_types, inputs.observed.node_types),
            ("relationship type", inputs.baseline.relationship_types, inputs.observed.relationship_types),
        ):
            now = {t.label: t.count for t in after}
            for t in before:
                if t.count == 0:
                    continue
                count = now.get(t.label, 0)
                drop = (t.count - count) / t.count
                if drop > self.max_drop:
                    drops.append(f"{kind} {t.label}: {t.count} -> {count} (-{drop * 100:.1f}%)")
        if drops:
            return self._outcome(False, *_capped(drops))
        return self._outcome(True)


GATE_TYPES: dict[str, type[Gate]] = {
    g.check: g for g in (OntologyDiffGate, ConformanceGate, MetricGate, CountDropGate)
}


def evaluate_gates(gates: Sequence[Gate], inputs: GateInputs) -> tuple[GateOutcome, ...]:
    """Every Gate's outcome, in definition order."""
    return tuple(gate.evaluate(inputs) for gate in gates)


def outcome_to_dict(outcome: GateOutcome) -> dict[str, Any]:
    return {"gate": outcome.gate.to_dict(), "passed": outcome.passed, "reasons": list(outcome.reasons)}


def outcome_from_dict(d: Mapping[str, Any]) -> GateOutcome:
    return GateOutcome(
        gate=gate_from_dict(d["gate"]), passed=bool(d["passed"]), reasons=tuple(d["reasons"])
    )


# --- Parsing ---------------------------------------------------------------------------


def gate_from_dict(d: Mapping[str, Any]) -> Gate:
    if not isinstance(d, Mapping):
        raise GateConfigError(f"A Gate must be a mapping, got {d!r}")
    check = d.get("check")
    if check not in GATE_TYPES:
        raise GateConfigError(
            f"Gate {d.get('name', '?')!r}: unknown check {check!r} "
            f"(expected one of {', '.join(sorted(GATE_TYPES))})"
        )
    name = d.get("name", check)
    if not isinstance(name, str) or not name:
        raise GateConfigError(f"Gate name must be a non-empty string, got {name!r}")
    params = {k: v for k, v in d.items() if k not in ("name", "check")}
    return _PARSERS[check](name, _Params(name, params))


def parse_gates(section: Any) -> tuple[Gate, ...]:
    """The `gates:` section (a list of Gate mappings)."""
    if section is None:
        return ()
    if not isinstance(section, list):
        raise GateConfigError("'gates' must be a list of Gates")
    gates = tuple(gate_from_dict(d) for d in section)
    names = [g.name for g in gates]
    duplicates = sorted({n for n in names if names.count(n) > 1})
    if duplicates:
        raise GateConfigError(f"Duplicate Gate names: {', '.join(duplicates)}")
    return gates


GatesInput = str | os.PathLike[str] | Sequence[Gate]


def load_gates(gates: GatesInput) -> tuple[Gate, ...]:
    """Gates from a config file path, config YAML text, or already-built Gates."""
    if isinstance(gates, os.PathLike):
        from stetiq.config import load_config

        try:
            config = load_config(gates)
        except (OSError, ValueError, yaml.YAMLError) as e:
            raise GateConfigError(f"Cannot read config file {gates}: {e}") from None
        return parse_gates(config.get("gates"))
    if isinstance(gates, str):
        try:
            config = yaml.safe_load(gates)
        except yaml.YAMLError as e:
            raise GateConfigError(f"Malformed config YAML: {e}") from None
        if not isinstance(config, Mapping):
            raise GateConfigError("The stetiq config must be a YAML mapping")
        return parse_gates(config.get("gates"))
    return tuple(gates)


@dataclass
class _Params:
    gate: str
    values: dict[str, Any]
    used: set[str] = field(default_factory=set)

    def get(self, key: str, default: Any = ..., *, kind: type | tuple[type, ...] = object) -> Any:
        self.used.add(key)
        if key not in self.values:
            if default is ...:
                raise GateConfigError(f"Gate {self.gate!r}: missing {key!r}")
            return default
        value = self.values[key]
        if isinstance(value, bool) and bool not in (kind if isinstance(kind, tuple) else (kind,)):
            raise GateConfigError(f"Gate {self.gate!r}: {key!r} has an invalid value {value!r}")
        if not isinstance(value, kind):
            raise GateConfigError(f"Gate {self.gate!r}: {key!r} has an invalid value {value!r}")
        return value

    def done(self) -> None:
        unknown = sorted(set(self.values) - self.used)
        if unknown:
            raise GateConfigError(f"Gate {self.gate!r}: unknown key(s) {', '.join(unknown)}")


def _parse_diff(name: str, p: _Params) -> Gate:
    raw = p.get("max_classification", kind=str)
    try:
        classification = Classification(raw)
    except ValueError:
        raise GateConfigError(
            f"Gate {name!r}: max_classification must be additive, deprecating or breaking"
        ) from None
    p.done()
    return OntologyDiffGate(name=name, max_classification=classification)


def _number(p: _Params, key: str, default: Any = ...) -> float | None:
    value = p.get(key, default, kind=(int, float))
    return None if value is None else float(value)


def _parse_conformance(name: str, p: _Params) -> Gate:
    score = _number(p, "min_score")
    if not 0.0 <= score <= 1.0:
        raise GateConfigError(f"Gate {name!r}: min_score must be between 0 and 1")
    p.done()
    return ConformanceGate(name=name, min_score=score)


def _parse_metric(name: str, p: _Params) -> Gate:
    evaluator = p.get("evaluator", kind=str)
    metric = p.get("metric", kind=str)
    low, high = _number(p, "min", None), _number(p, "max", None)
    if low is None and high is None:
        raise GateConfigError(f"Gate {name!r}: give 'min' and/or 'max'")
    if low is not None and high is not None and low > high:
        raise GateConfigError(f"Gate {name!r}: min is greater than max")
    parameters = p.get("parameters", None, kind=dict)
    p.done()
    return MetricGate(
        name=name, evaluator=evaluator, metric=metric, min=low, max=high, parameters=parameters
    )


def _parse_count_drop(name: str, p: _Params) -> Gate:
    drop = _number(p, "max_drop")
    if not 0.0 <= drop <= 1.0:
        raise GateConfigError(f"Gate {name!r}: max_drop must be a fraction between 0 and 1")
    p.done()
    return CountDropGate(name=name, max_drop=drop)


_PARSERS = {
    "ontology_diff": _parse_diff,
    "conformance": _parse_conformance,
    "metric": _parse_metric,
    "count_drop": _parse_count_drop,
}

