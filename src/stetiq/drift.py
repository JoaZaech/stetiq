"""Drift engine: pure function of (contract Ontology, Observed Schema, previous Observed
Schema, thresholds, Baseline Observation's Observed Schema) -> Drift findings and the
checks that were not comparable. No I/O.

Drift is a divergence, found by an Observation, between a Graph Source's Observed Schema
and the Contract Alias's Ontology Version. It has two parts:

- **structural**: Concepts (Classes, Relations, Attributes) observed but not declared by
  the contract (`undeclared`), or declared but no longer observed (`vanished`); and values
  of a Vocabulary-bound Attribute outside the contract's Vocabulary (`undeclared_value`,
  one per value). This reuses the Conformance engine, so "is X declared" means exactly
  what it means for a run's Conformance (inherited Attributes, etc.).
- **statistical**: a node or relationship type's or a pattern's count changing, relative
  to the previous Observation, by more than the configured fraction (`count_drop`,
  `count_increase`), off unless a threshold is set; a Violation Rate rising more than
  `max_violation_increase` (absolute points) above its value in the Baseline Observation
  (`violation_increase`), on by default; a declared pattern's Coverage falling more than
  `max_coverage_drop` (absolute points) below its baseline value (`coverage_drop`), off
  unless set; and a declared, not-required Attribute's fill rate falling more than
  `max_fill_rate_drop` below its baseline value (`fill_rate_drop`), off unless set.
  Counts compare with the previous Observation, ratios with the baseline (ADR 0013).

A check that lacks its input (a rate the baseline cannot give, a truncated value list, a
type, pattern or owner below `min_count`) never raises a finding: it is reported as
`NotComparable` instead.

Thresholds come from the `drift:` section of the repo config (`stetiq.yaml`), see
`thresholds_from_config`.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
from enum import StrEnum
from typing import Any

from stetiq.conformance import (
    Conformance,
    MismatchKind,
    MismatchSubjectKind,
    _properties_of,
    assess_conformance,
)
from stetiq.errors import InvalidDriftConfigError
from stetiq.graph_source import ObservedSchema
from stetiq.ontology import Ontology
from stetiq.ontology.model import Direction, Pattern

# `max_violation_increase` when `stetiq.yaml`, a request or the SDK leaves it out.
DEFAULT_MAX_VIOLATION_INCREASE = 0.01


class DriftKind(StrEnum):
    UNDECLARED = "undeclared"  # observed, not declared by the contract
    VANISHED = "vanished"  # declared by the contract, not observed
    UNDECLARED_VALUE = "undeclared_value"  # a value outside the contract's Vocabulary
    COUNT_DROP = "count_drop"  # count fell beyond `max_count_drop` since the previous Observation
    COUNT_INCREASE = "count_increase"  # count rose beyond `max_count_increase`
    # a Violation Rate rose beyond `max_violation_increase` above the Baseline Observation's
    VIOLATION_INCREASE = "violation_increase"
    # a declared pattern's Coverage fell beyond `max_coverage_drop` below the baseline's
    COVERAGE_DROP = "coverage_drop"
    # an optional Attribute's fill rate fell beyond `max_fill_rate_drop` below the baseline's
    FILL_RATE_DROP = "fill_rate_drop"


@dataclass(frozen=True)
class DriftFinding:
    """One divergence. `previous_count` / `observed_count` are set for count findings.

    `undeclared_value` carries the value, how many owners hold it (`count`) and their share
    of the owner (`share`, None when the value list was truncated). `violation_increase`
    carries the Conformance check (`violation`) and its Violation Rate in the Baseline
    Observation and now (`baseline_rate`, `observed_rate`); for a `cardinality_violation`
    on a pattern, `direction` says which degree (`out` or `in`). `coverage_drop` carries the
    degree (`direction`: `out` over the source nodes, `in` over the target nodes) and its
    Coverage in the Baseline Observation and now (`baseline_rate`, `observed_rate`)."""

    kind: DriftKind
    subject: str  # a label, `Owner.property`, or a pattern `(Source)-[REL]->(Target)`
    subject_kind: MismatchSubjectKind
    detail: str = ""
    previous_count: int | None = None
    observed_count: int | None = None
    value: str | None = None  # set for `undeclared_value`: the value itself
    count: int | None = None
    share: float | None = None
    violation: MismatchKind | None = None
    baseline_rate: float | None = None
    observed_rate: float | None = None
    direction: Direction | None = None
    # False when the previous Observation already had it (see `mark_new`). Findings stored
    # before this distinction read as new: each of them made `stetiq observe` exit 3.
    new: bool = True

    @property
    def structural(self) -> bool:
        return self.kind in _STRUCTURAL.values()

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "kind": self.kind.value,
            "subject": self.subject,
            "subject_kind": self.subject_kind,
            "detail": self.detail,
            "previous_count": self.previous_count,
            "observed_count": self.observed_count,
            "new": self.new,
        }
        optional = {
            "value": self.value,
            "count": self.count,
            "share": self.share,
            "violation": None if self.violation is None else self.violation.value,
            "baseline_rate": self.baseline_rate,
            "observed_rate": self.observed_rate,
            "direction": self.direction,
        }
        d.update({k: v for k, v in optional.items() if v is not None})
        return d

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> DriftFinding:
        violation = d.get("violation")
        return cls(
            kind=DriftKind(d["kind"]),
            subject=d["subject"],
            subject_kind=d["subject_kind"],
            detail=d.get("detail", ""),
            previous_count=d.get("previous_count"),
            observed_count=d.get("observed_count"),
            value=d.get("value"),
            count=d.get("count"),
            share=d.get("share"),
            violation=None if violation is None else MismatchKind(violation),
            baseline_rate=d.get("baseline_rate"),
            observed_rate=d.get("observed_rate"),
            direction=d.get("direction"),
            new=d.get("new", True),
        )


@dataclass(frozen=True)
class NotComparable:
    """A Drift check that lacked its input, so it raised no finding: `check` is the finding
    kind it would have raised, `violation` the Conformance check behind a Violation Rate,
    and `reason` says what was missing."""

    check: DriftKind
    subject: str
    subject_kind: MismatchSubjectKind
    reason: str
    violation: MismatchKind | None = None

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "check": self.check.value,
            "subject": self.subject,
            "subject_kind": self.subject_kind,
            "reason": self.reason,
        }
        if self.violation is not None:
            d["violation"] = self.violation.value
        return d

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> NotComparable:
        violation = d.get("violation")
        return cls(
            check=DriftKind(d["check"]),
            subject=d["subject"],
            subject_kind=d["subject_kind"],
            reason=d["reason"],
            violation=None if violation is None else MismatchKind(violation),
        )


@dataclass(frozen=True)
class DriftAssessment:
    """What `assess_drift` found: the findings (empty means no Drift) and the checks that
    were not comparable."""

    findings: tuple[DriftFinding, ...] = ()
    not_comparable: tuple[NotComparable, ...] = ()


@dataclass(frozen=True)
class DriftThresholds:
    """Statistical Drift thresholds. The count ones are fractions of the previous count
    (0.1 = 10%) and off by default; `max_violation_increase` is in absolute points of a
    Violation Rate above the Baseline Observation's (0.01 = one percentage point) and
    defaults to `DEFAULT_MAX_VIOLATION_INCREASE`; `max_coverage_drop` is in absolute points
    of a declared pattern's Coverage below the Baseline Observation's and off by default.

    None disables that check. A change exactly at the threshold is not Drift."""

    max_count_drop: float | None = None
    max_count_increase: float | None = None
    max_violation_increase: float | None = DEFAULT_MAX_VIOLATION_INCREASE
    max_coverage_drop: float | None = None
    max_fill_rate_drop: float | None = None
    # A type, pattern or owner with fewer than this many nodes or relationships is too small
    # for a statistical check: the check is not comparable instead.
    min_count: int = 0

    def __post_init__(self) -> None:
        if (
            isinstance(self.min_count, bool)
            or not isinstance(self.min_count, int)
            or self.min_count < 0
        ):
            raise InvalidDriftConfigError(
                f"drift.min_count must be a non-negative whole number, got {self.min_count!r}"
            )
        for name in _THRESHOLD_KEYS:
            value = getattr(self, name)
            if value is None:
                continue
            if isinstance(value, bool) or not isinstance(value, int | float) or value < 0:
                raise InvalidDriftConfigError(
                    f"drift.{name} must be a non-negative number (a fraction, e.g. 0.1), got {value!r}"
                )

    def to_dict(self) -> dict[str, Any]:
        return {name: getattr(self, name) for name in (*_THRESHOLD_KEYS, "min_count")}

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> DriftThresholds:
        """A missing key takes its default; an explicit None (`null`) turns the check off."""
        return cls(
            max_count_drop=d.get("max_count_drop"),
            max_count_increase=d.get("max_count_increase"),
            max_violation_increase=d.get("max_violation_increase", DEFAULT_MAX_VIOLATION_INCREASE),
            max_coverage_drop=d.get("max_coverage_drop"),
            max_fill_rate_drop=d.get("max_fill_rate_drop"),
            min_count=d.get("min_count", 0),
        )


_THRESHOLD_KEYS = (
    "max_count_drop",
    "max_count_increase",
    "max_violation_increase",
    "max_coverage_drop",
    "max_fill_rate_drop",
)


def thresholds_from_config(config: Mapping[str, Any]) -> DriftThresholds:
    """The `drift:` section of a repo config mapping (as from `stetiq.config.load_config`).

    ```yaml
    drift:
      max_count_drop: 0.1      # a type's count falling by more than 10% is Drift
      max_count_increase: 0.5  # optional
      max_violation_increase: 0.02  # default 0.01; null turns it off
      max_coverage_drop: 0.05  # optional
    ```
    A missing section or key takes its default: the count checks off, the Violation Rate
    check at 0.01 (structural Drift always applies)."""
    section = config.get("drift")
    if section is None:
        return DriftThresholds()
    if not isinstance(section, Mapping):
        raise InvalidDriftConfigError(f"drift: must be a mapping, got {section!r}")
    keys = {*_THRESHOLD_KEYS, "min_count"}
    unknown = sorted(set(section) - keys)
    if unknown:
        raise InvalidDriftConfigError(
            f"drift: unknown key(s) {', '.join(map(str, unknown))} "
            f"(expected {', '.join(sorted(keys))})"
        )
    return DriftThresholds.from_dict(section)


_STRUCTURAL = {
    MismatchKind.UNDECLARED: DriftKind.UNDECLARED,
    MismatchKind.ABSENT: DriftKind.VANISHED,
    MismatchKind.VALUE_OUTSIDE_VOCABULARY: DriftKind.UNDECLARED_VALUE,
}

# The Conformance checks whose Violation Rate Drift compares with the baseline.
# `value_outside_vocabulary` has a rate too, but its Drift is `undeclared_value`.
_RATED = (
    MismatchKind.REQUIRED_MISSING,
    MismatchKind.TYPE_MISMATCH,
    MismatchKind.CARDINALITY_VIOLATION,
)


def assess_drift(
    contract: Ontology,
    observed: ObservedSchema,
    previous: ObservedSchema | None = None,
    thresholds: DriftThresholds | None = None,
    baseline: ObservedSchema | None = None,
) -> DriftAssessment:
    """Every Drift finding, structural first (in Conformance order), then statistical:
    count changes since `previous` (node types, relationship types, then patterns, by
    label), Violation Rates risen since `baseline` (in Conformance order), declared
    patterns' Coverage fallen since `baseline` (in contract order, out-degree before
    in-degree), then fill rates fallen since `baseline` (node types, then relationship
    types). No `thresholds` turns every statistical check off; no `baseline` (this
    Observation is its own) leaves no rate to compare."""
    conformance = assess_conformance(contract, observed)
    findings = [
        DriftFinding(
            kind=_STRUCTURAL[m.kind],
            subject=m.subject,
            subject_kind=m.subject_kind,
            detail=m.detail,
            value=m.value,
            count=m.count,
            share=m.rate,
        )
        for m in conformance.mismatches
        if m.kind in _STRUCTURAL and m.subject_kind != "pattern"  # patterns are not Concepts
    ]
    not_comparable = [
        NotComparable(
            check=DriftKind.UNDECLARED_VALUE,
            subject=m.subject,
            subject_kind=m.subject_kind,
            reason="value list truncated, so the values' share of the owner is unknown",
        )
        for m in conformance.mismatches
        if m.kind == MismatchKind.VALUE_OUTSIDE_VOCABULARY and m.rate is None
    ]
    if previous is not None and thresholds is not None:
        count_findings, count_gaps = _statistical(observed, previous, thresholds)
        findings.extend(count_findings)
        not_comparable.extend(count_gaps)
    min_count = 0 if thresholds is None else thresholds.min_count
    limit = None if thresholds is None else thresholds.max_violation_increase
    if baseline is not None and limit is not None:
        rate_findings, rate_gaps = _violation_increases(
            contract,
            conformance,
            assess_conformance(contract, baseline),
            observed,
            baseline,
            limit,
            min_count,
        )
        findings.extend(rate_findings)
        not_comparable.extend(rate_gaps)
    coverage_limit = None if thresholds is None else thresholds.max_coverage_drop
    if baseline is not None and coverage_limit is not None:
        coverage_findings, coverage_gaps = _coverage_drops(
            contract, observed, baseline, coverage_limit, min_count
        )
        findings.extend(coverage_findings)
        not_comparable.extend(coverage_gaps)
    fill_limit = None if thresholds is None else thresholds.max_fill_rate_drop
    if baseline is not None and fill_limit is not None:
        fill_findings, fill_gaps = _fill_rate_drops(
            contract, observed, baseline, fill_limit, min_count
        )
        findings.extend(fill_findings)
        not_comparable.extend(fill_gaps)
    # One entry per check: a truncated list yields one mismatch per listed outside value.
    return DriftAssessment(tuple(findings), tuple(dict.fromkeys(not_comparable)))


def _violation_increases(
    contract: Ontology,
    conformance: Conformance,
    at_baseline: Conformance,
    observed: ObservedSchema,
    baseline: ObservedSchema,
    limit: float,
    min_count: int,
) -> tuple[list[DriftFinding], list[NotComparable]]:
    """A finding per Violation Rate more than `limit` above its baseline value. A check
    the baseline passed had rate 0; one it could not run (its subject was not observed
    then), whose rate is unknown on either side, or whose owner (a pattern's: the endpoint
    nodes of the failing degree) is below `min_count` on either side, is not comparable."""
    patterns = {str(p): p for p in contract.patterns}  # a rated pattern is a declared one
    # A pattern's out- and in-degree are separate checks on the same subject.
    before = {
        (m.kind, m.subject, m.direction): m.rate for m in at_baseline.mismatches if m.kind in _RATED
    }
    findings: list[DriftFinding] = []
    gaps: list[NotComparable] = []
    for m in conformance.mismatches:
        if m.kind not in _RATED:
            continue
        if (m.kind, m.subject, m.direction) in before:
            then = before[(m.kind, m.subject, m.direction)]
        else:
            then = 0.0 if _observed_in(baseline, m.subject_kind, m.subject) else None
        if m.rate is None or then is None:
            side = "this Observation" if m.rate is None else "the Baseline Observation"
            gaps.append(
                NotComparable(
                    check=DriftKind.VIOLATION_INCREASE,
                    subject=m.subject,
                    subject_kind=m.subject_kind,
                    reason=f"no Violation Rate in {side}",
                    violation=m.kind,
                )
            )
            continue
        if m.subject_kind == "pattern" and m.direction is not None:
            small = _endpoint_min_count_gap(
                DriftKind.VIOLATION_INCREASE,
                patterns[m.subject],
                m.direction,
                min_count,
                baseline,
                observed,
                m.kind,
            )
        else:
            small = baseline_min_count_gap(
                DriftKind.VIOLATION_INCREASE,
                m.subject,
                m.subject_kind,
                min_count,
                baseline,
                observed,
                m.kind,
            )
        if small is not None:
            gaps.append(small)
            continue
        # Rounded, so that a rise of exactly the threshold is not Drift despite float error.
        if round(m.rate - then, 9) > limit:
            findings.append(
                DriftFinding(
                    kind=DriftKind.VIOLATION_INCREASE,
                    subject=m.subject,
                    subject_kind=m.subject_kind,
                    detail=f"{m.kind}{_direction(m.direction)} rate rose from {then:.1%} "
                    f"to {m.rate:.1%} since the Baseline Observation",
                    violation=m.kind,
                    baseline_rate=then,
                    observed_rate=m.rate,
                    direction=m.direction,
                )
            )
    return findings, gaps


def _coverage_drops(
    contract: Ontology,
    observed: ObservedSchema,
    baseline: ObservedSchema,
    limit: float,
    min_count: int,
) -> tuple[list[DriftFinding], list[NotComparable]]:
    """A finding per declared pattern and degree whose Coverage is more than `limit` below
    its baseline value. A degree whose endpoint type is not observed now has nothing to
    cover and is skipped; one whose Coverage is unknown on either side, or whose endpoint
    type (the nodes it is a share of) is below `min_count` on either side, is not
    comparable."""
    findings: list[DriftFinding] = []
    gaps: list[NotComparable] = []
    for declared in contract.patterns:
        subject = str(declared)
        for direction, endpoint in declared.directions:
            if not _count(observed, endpoint):
                continue
            now = _coverage(observed, declared, direction)
            then = _coverage(baseline, declared, direction)
            if now is None or then is None:
                side = "this Observation" if now is None else "the Baseline Observation"
                gaps.append(
                    NotComparable(
                        check=DriftKind.COVERAGE_DROP,
                        subject=subject,
                        subject_kind="pattern",
                        reason=f"no {direction}-degree Coverage in {side}",
                    )
                )
                continue
            small = _endpoint_min_count_gap(
                DriftKind.COVERAGE_DROP, declared, direction, min_count, baseline, observed
            )
            if small is not None:
                gaps.append(small)
                continue
            # Rounded, so that a drop of exactly the threshold is not Drift despite float error.
            if round(then - now, 9) > limit:
                findings.append(
                    DriftFinding(
                        kind=DriftKind.COVERAGE_DROP,
                        subject=subject,
                        subject_kind="pattern",
                        detail=f"{direction}-degree Coverage fell from {then:.1%} to {now:.1%} "
                        "since the Baseline Observation",
                        baseline_rate=then,
                        observed_rate=now,
                        direction=direction,
                    )
                )
    return findings, gaps


def _count(schema: ObservedSchema, label: str) -> int:
    node_type = schema.node_type(label)
    return 0 if node_type is None else node_type.count


def _coverage(schema: ObservedSchema, declared: Pattern, direction: Direction) -> float | None:
    """The share of the pattern's `direction` endpoint nodes with at least one such
    relationship: None when no such node was observed or the degree lacks `with_edges`."""
    endpoints = _count(schema, declared.endpoint(direction))
    if not endpoints:
        return None
    pattern = schema.pattern(declared.source, declared.relationship, declared.target)
    if pattern is None:
        return 0.0  # endpoint nodes, but no such relationship between them
    with_edges = pattern.degree(direction).with_edges
    return None if with_edges is None else with_edges / endpoints


def _direction(direction: str | None) -> str:
    return "" if direction is None else f" ({direction}-degree)"


def _fill_rate_drops(
    contract: Ontology,
    observed: ObservedSchema,
    baseline: ObservedSchema,
    limit: float,
    min_count: int,
) -> tuple[list[DriftFinding], list[NotComparable]]:
    """A finding per declared, not-required Attribute whose fill rate is more than `limit`
    below its baseline value (a required one has its Violation Rate instead). An Attribute
    not observed on an observed owner has fill rate 0; an owner not observed now is
    `vanished` Drift, and one the baseline did not observe, or below `min_count` on either
    side, is not comparable."""
    properties_of = _properties_of(contract)
    owners: tuple[tuple[Any, Any], ...] = (
        (contract.node_types, ObservedSchema.node_type),
        (contract.relationship_types, ObservedSchema.relationship_type),
    )
    findings: list[DriftFinding] = []
    gaps: list[NotComparable] = []
    for declared, find in owners:
        for concept in sorted(declared, key=lambda c: c.label):
            now, then = find(observed, concept.label), find(baseline, concept.label)
            if now is None:
                continue
            for prop in sorted(properties_of(concept), key=lambda p: p.name):
                if prop.required:
                    continue
                subject = f"{concept.label}.{prop.name}"
                if then is None:
                    gaps.append(
                        NotComparable(
                            check=DriftKind.FILL_RATE_DROP,
                            subject=subject,
                            subject_kind="property",
                            reason=f"{concept.label} not observed in the Baseline Observation",
                        )
                    )
                    continue
                small = baseline_min_count_gap(
                    DriftKind.FILL_RATE_DROP, subject, "property", min_count, baseline, observed
                )
                if small is not None:
                    gaps.append(small)
                    continue
                before, after = _fill_rate(then, prop.name), _fill_rate(now, prop.name)
                # Rounded, so that a drop of exactly the threshold is not Drift.
                if round(before - after, 9) > limit:
                    findings.append(
                        DriftFinding(
                            kind=DriftKind.FILL_RATE_DROP,
                            subject=subject,
                            subject_kind="property",
                            detail=f"fill rate fell from {before:.1%} to {after:.1%} "
                            "since the Baseline Observation",
                            baseline_rate=before,
                            observed_rate=after,
                        )
                    )
    return findings, gaps


def _fill_rate(owner: Any, name: str) -> float:
    return next((p.fill_rate for p in owner.properties if p.name == name), 0.0)


def _observed_in(schema: ObservedSchema, subject_kind: MismatchSubjectKind, subject: str) -> bool:
    """Whether `schema` observed the subject of a check: a pattern, or an Attribute
    `Owner.name` on a node or relationship type."""
    if subject_kind == "pattern":
        return any(str(p.pattern) == subject for p in schema.patterns)
    owner, _, name = subject.partition(".")
    owners = (schema.node_type(owner), schema.relationship_type(owner))
    return any(o is not None and any(p.name == name for p in o.properties) for o in owners)


def _statistical(
    observed: ObservedSchema, previous: ObservedSchema, thresholds: DriftThresholds
) -> tuple[list[DriftFinding], list[NotComparable]]:
    findings: list[DriftFinding] = []
    gaps: list[NotComparable] = []
    checks = [
        kind
        for kind, limit in (
            (DriftKind.COUNT_DROP, thresholds.max_count_drop),
            (DriftKind.COUNT_INCREASE, thresholds.max_count_increase),
        )
        if limit is not None
    ]
    counted: tuple[tuple[MismatchSubjectKind, dict[str, int], dict[str, int]], ...] = (
        ("node_type", _counts(previous.node_types), _counts(observed.node_types)),
        (
            "relationship_type",
            _counts(previous.relationship_types),
            _counts(observed.relationship_types),
        ),
        ("pattern", _pattern_counts(previous), _pattern_counts(observed)),
    )
    for subject_kind, before, after in counted:
        for label in sorted(before.keys() | after.keys()):
            old, new = before.get(label, 0), after.get(label, 0)
            if old == 0:
                continue  # nothing to compare a relative change with
            small = [
                min_count_gap(
                    check,
                    label,
                    subject_kind,
                    old,
                    thresholds.min_count,
                    "the previous Observation",
                )
                for check in checks
            ]
            if any(small):
                gaps.extend(g for g in small if g is not None)
                continue
            change = (new - old) / old
            if thresholds.max_count_drop is not None and -change > thresholds.max_count_drop:
                kind, word = DriftKind.COUNT_DROP, "dropped"
            elif (
                thresholds.max_count_increase is not None and change > thresholds.max_count_increase
            ):
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
    return findings, gaps


def min_count_gap(
    check: DriftKind,
    subject: str,
    subject_kind: MismatchSubjectKind,
    count: int,
    min_count: int,
    where: str,
    violation: MismatchKind | None = None,
) -> NotComparable | None:
    """The `min_count` floor of every statistical check: the not-comparable entry for a
    check whose type, pattern or owner had only `count` nodes or relationships in `where`
    (e.g. "the Baseline Observation"), or None when `count` reaches `min_count`. Use
    `owner_count` for the count."""
    if count >= min_count:
        return None
    return NotComparable(
        check=check,
        subject=subject,
        subject_kind=subject_kind,
        reason=f"{count} in {where}, below min_count ({min_count})",
        violation=violation,
    )


def baseline_min_count_gap(
    check: DriftKind,
    subject: str,
    subject_kind: MismatchSubjectKind,
    min_count: int,
    baseline: ObservedSchema,
    observed: ObservedSchema,
    violation: MismatchKind | None = None,
) -> NotComparable | None:
    """`min_count_gap` for a ratio check compared with the Baseline Observation, which
    needs enough owners (see `owner_count`) both there and in this Observation."""
    for schema, where in ((baseline, "the Baseline Observation"), (observed, "this Observation")):
        count = owner_count(schema, subject_kind, subject)
        gap = min_count_gap(check, subject, subject_kind, count, min_count, where, violation)
        if gap is not None:
            return gap
    return None


def _endpoint_min_count_gap(
    check: DriftKind,
    declared: Pattern,
    direction: Direction,
    min_count: int,
    baseline: ObservedSchema,
    observed: ObservedSchema,
    violation: MismatchKind | None = None,
) -> NotComparable | None:
    """`baseline_min_count_gap` for a pattern's degree, whose owners are the degree's
    endpoint nodes (the source for `out`, the target for `in`), not its relationships."""
    endpoint = declared.endpoint(direction)
    small = baseline_min_count_gap(
        check, endpoint, "node_type", min_count, baseline, observed, violation
    )
    if small is None:
        return None
    # The floor is on the endpoint nodes; the check is still the pattern's.
    return replace(
        small,
        subject=str(declared),
        subject_kind="pattern",
        reason=f"{direction}-degree endpoint {endpoint}: {small.reason}",
    )


def owner_count(schema: ObservedSchema, subject_kind: MismatchSubjectKind, subject: str) -> int:
    """How many nodes or relationships a check's subject counts in `schema`, for
    `min_count`: a type's own count, an Attribute `Owner.name`'s owner's count; 0 when not
    observed. A pattern's degree counts its endpoint nodes (`_endpoint_min_count_gap`)."""
    label = subject.partition(".")[0] if subject_kind == "property" else subject
    owner = schema.node_type(label) if subject_kind != "relationship_type" else None
    if owner is None and subject_kind != "node_type":
        owner = schema.relationship_type(label)
    return 0 if owner is None else owner.count


def _counts(types: Any) -> dict[str, int]:
    return {t.label: t.count for t in types}


def _pattern_counts(schema: ObservedSchema) -> dict[str, int]:
    return {str(p.pattern): p.count for p in schema.patterns}


def mark_new(
    findings: tuple[DriftFinding, ...], previous: tuple[DriftFinding, ...]
) -> tuple[DriftFinding, ...]:
    """`findings` with each marked new or persisting by comparison with `previous`, the
    previous Observation's findings. A finding persists when `previous` has one with the
    same identity (`_identity`), and, for a rate finding, when its rate has not worsened
    since: moved further from the baseline in the direction it drifted. A count finding
    is always new, since it is itself a change since the previous Observation."""
    before = {_identity(f): f for f in previous}
    return tuple(replace(f, new=_is_new(f, before.get(_identity(f)))) for f in findings)


def _identity(f: DriftFinding) -> tuple[Any, ...]:
    """What makes two Observations' findings the same one, whatever its kind. A pattern's
    out- and in-degree findings (Coverage, cardinality) differ only by `direction`."""
    return (f.kind, f.subject, f.subject_kind, f.value, f.violation, f.direction)


def _is_new(f: DriftFinding, before: DriftFinding | None) -> bool:
    if before is None or f.previous_count is not None:
        return True
    if f.observed_rate is None or f.baseline_rate is None or before.observed_rate is None:
        return False
    direction = 1 if f.observed_rate >= f.baseline_rate else -1
    # Rounded, so that float error is not a worsening.
    return round((f.observed_rate - before.observed_rate) * direction, 9) > 0
