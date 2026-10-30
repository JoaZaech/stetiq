"""Drift engine: pure function of (contract Ontology, Observed Schema, previous Observed
Schema, thresholds) -> Drift findings. No I/O.

Drift is a divergence, found by an Observation, between a Graph Source's Observed Schema
and the Contract Alias's Ontology Version. It has two parts:

- **structural**: Concepts (node types, relationship types, properties) observed but not
  declared by the contract (`undeclared`), or declared but no longer observed
  (`vanished`). This reuses the Conformance engine, so "is X declared" means exactly
  what it means for a run's Conformance (inherited properties, etc.).
- **statistical**: a node or relationship type's count changing, relative to the
  previous Observation, by more than the configured fraction (`count_drop`,
  `count_increase`). Off unless a threshold is set.

Thresholds come from the `drift:` section of the repo config (`stetiq.yaml`), see
`thresholds_from_config`.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Literal

from stetiq.conformance import MismatchKind, assess_conformance
from stetiq.errors import InvalidDriftConfigError
from stetiq.graph_source import ObservedSchema
from stetiq.ontology import Ontology

SubjectKind = Literal["node_type", "relationship_type", "property"]


class DriftKind(StrEnum):
    UNDECLARED = "undeclared"  # observed, not declared by the contract
    VANISHED = "vanished"  # declared by the contract, not observed
    COUNT_DROP = "count_drop"  # count fell beyond `max_count_drop` since the previous Observation
    COUNT_INCREASE = "count_increase"  # count rose beyond `max_count_increase`


@dataclass(frozen=True)
class DriftFinding:
    """One divergence. `previous_count` / `observed_count` are set for statistical findings."""

    kind: DriftKind
    subject: str  # a label, or `Owner.property`
    subject_kind: SubjectKind
    detail: str = ""
    previous_count: int | None = None
    observed_count: int | None = None

    @property
    def structural(self) -> bool:
        return self.kind in (DriftKind.UNDECLARED, DriftKind.VANISHED)

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind.value,
            "subject": self.subject,
            "subject_kind": self.subject_kind,
            "detail": self.detail,
            "previous_count": self.previous_count,
            "observed_count": self.observed_count,
        }

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> DriftFinding:
        return cls(
            kind=DriftKind(d["kind"]),
            subject=d["subject"],
            subject_kind=d["subject_kind"],
            detail=d.get("detail", ""),
            previous_count=d.get("previous_count"),
            observed_count=d.get("observed_count"),
        )


@dataclass(frozen=True)
class DriftThresholds:
    """Statistical Drift thresholds, as fractions of the previous count (0.1 = 10%).

    None disables that check. A change exactly at the threshold is not Drift."""

    max_count_drop: float | None = None
    max_count_increase: float | None = None

    def __post_init__(self) -> None:
        for name in ("max_count_drop", "max_count_increase"):
            value = getattr(self, name)
            if value is None:
                continue
            if isinstance(value, bool) or not isinstance(value, int | float) or value < 0:
                raise InvalidDriftConfigError(
                    f"drift.{name} must be a non-negative number (a fraction, e.g. 0.1), got {value!r}"
                )

    def to_dict(self) -> dict[str, Any]:
        return {"max_count_drop": self.max_count_drop, "max_count_increase": self.max_count_increase}

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> DriftThresholds:
        return cls(
            max_count_drop=d.get("max_count_drop"),
            max_count_increase=d.get("max_count_increase"),
        )


_THRESHOLD_KEYS = {"max_count_drop", "max_count_increase"}


def thresholds_from_config(config: Mapping[str, Any]) -> DriftThresholds:
    """The `drift:` section of a repo config mapping (as from `stetiq.config.load_config`).

    ```yaml
    drift:
      max_count_drop: 0.1      # a type's count falling by more than 10% is Drift
      max_count_increase: 0.5  # optional
    ```
    A missing section means no statistical thresholds (structural Drift still applies)."""
    section = config.get("drift")
    if section is None:
        return DriftThresholds()
    if not isinstance(section, Mapping):
        raise InvalidDriftConfigError(f"drift: must be a mapping, got {section!r}")
    unknown = sorted(set(section) - _THRESHOLD_KEYS)
    if unknown:
        raise InvalidDriftConfigError(
            f"drift: unknown key(s) {', '.join(map(str, unknown))} "
            f"(expected {', '.join(sorted(_THRESHOLD_KEYS))})"
        )
    return DriftThresholds.from_dict(section)


_STRUCTURAL = {MismatchKind.UNDECLARED: DriftKind.UNDECLARED, MismatchKind.ABSENT: DriftKind.VANISHED}


def assess_drift(
    contract: Ontology,
    observed: ObservedSchema,
    previous: ObservedSchema | None = None,
    thresholds: DriftThresholds | None = None,
) -> tuple[DriftFinding, ...]:
    """Every Drift finding, structural first (in Conformance order), then statistical
    (node types, then relationship types, by label). Empty means no Drift."""
    conformance = assess_conformance(contract, observed)
    findings = [
        DriftFinding(
            kind=_STRUCTURAL[m.kind], subject=m.subject, subject_kind=m.subject_kind, detail=m.detail
        )
        for m in conformance.mismatches
        if m.kind in _STRUCTURAL and m.subject_kind != "pattern"  # patterns are not Concepts
    ]
    if previous is not None and thresholds is not None:
        findings.extend(_statistical(observed, previous, thresholds))
    return tuple(findings)


def _statistical(
    observed: ObservedSchema, previous: ObservedSchema, thresholds: DriftThresholds
) -> list[DriftFinding]:
    findings = []
    kinds: tuple[tuple[SubjectKind, str], ...] = (
        ("node_type", "node_types"),
        ("relationship_type", "relationship_types"),
    )
    for subject_kind, attr in kinds:
        before = {t.label: t.count for t in getattr(previous, attr)}
        after = {t.label: t.count for t in getattr(observed, attr)}
        for label in sorted(before.keys() | after.keys()):
            old, new = before.get(label, 0), after.get(label, 0)
            if old == 0:
                continue  # nothing to compare a relative change with
            change = (new - old) / old
            if thresholds.max_count_drop is not None and -change > thresholds.max_count_drop:
                kind, word = DriftKind.COUNT_DROP, "dropped"
            elif thresholds.max_count_increase is not None and change > thresholds.max_count_increase:
                kind, word = DriftKind.COUNT_INCREASE, "rose"
            else:
                continue
            findings.append(
                DriftFinding(
                    kind=kind,
                    subject=label,
                    subject_kind=subject_kind,
                    detail=f"count {word} from {old} to {new} ({change:+.0%})",
                    previous_count=old,
                    observed_count=new,
                )
            )
    return findings
