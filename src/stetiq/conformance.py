"""Conformance engine: pure function of (Declared Ontology, Observed Schema) -> score + breakdown.

No I/O. `assess_conformance` scores how well an Observed Schema matches its Declared
Ontology and lists every mismatch; `candidate_ontology` builds the Declared Ontology
extended with the newly observed Concepts (what an evolving Construction Run proposes
as a Candidate).
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum
from typing import Any, Literal

from stetiq.graph_source import (
    ObservedNodeType,
    ObservedProperty,
    ObservedRelationshipType,
    ObservedSchema,
)
from stetiq.ontology import NodeType, Ontology, Pattern, Property, RelationshipType
from stetiq.ontology.diff import WIDENING_TYPE_CHANGES

# What a mismatch is about. Concepts are node types, relationship types and properties
# (identity `Owner.property`, as in the Ontology Diff); patterns are endpoint patterns
# `(Source)-[REL]->(Target)`, which are not Concepts of their own.
SubjectKind = Literal["node_type", "relationship_type", "property", "pattern"]


class MismatchKind(StrEnum):
    ABSENT = "absent"  # declared, not observed
    UNDECLARED = "undeclared"  # observed, not declared
    TYPE_MISMATCH = "type_mismatch"  # a property holds values of an undeclared type
    REQUIRED_MISSING = "required_missing"  # a required property is not set everywhere


@dataclass(frozen=True)
class Mismatch:
    subject: str
    subject_kind: SubjectKind
    kind: MismatchKind
    detail: str = ""


@dataclass(frozen=True)
class Conformance:
    """`score` in [0, 1] is the share of checks that hold (see `assess_conformance`);
    `mismatches` lists every check that does not, in a deterministic order."""

    score: float
    mismatches: tuple[Mismatch, ...] = ()

    @property
    def declared_absent(self) -> tuple[Mismatch, ...]:
        """Concepts (node types, relationship types, properties) declared but not observed."""
        return self._concepts(MismatchKind.ABSENT)

    @property
    def undeclared(self) -> tuple[Mismatch, ...]:
        """Concepts observed but not declared."""
        return self._concepts(MismatchKind.UNDECLARED)

    @property
    def pattern_mismatches(self) -> tuple[Mismatch, ...]:
        """Endpoint patterns declared but not observed, or observed but not declared."""
        return tuple(m for m in self.mismatches if m.subject_kind == "pattern")

    @property
    def property_mismatches(self) -> tuple[Mismatch, ...]:
        """Properties both declared and observed whose observed values break the declaration."""
        return tuple(
            m
            for m in self.mismatches
            if m.subject_kind == "property"
            and m.kind not in (MismatchKind.ABSENT, MismatchKind.UNDECLARED)
        )

    def _concepts(self, kind: MismatchKind) -> tuple[Mismatch, ...]:
        return tuple(
            m for m in self.mismatches if m.kind == kind and m.subject_kind != "pattern"
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "score": self.score,
            "mismatches": [
                {
                    "subject": m.subject,
                    "subject_kind": m.subject_kind,
                    "kind": str(m.kind),
                    "detail": m.detail,
                }
                for m in self.mismatches
            ],
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Conformance:
        return cls(
            score=float(d["score"]),
            mismatches=tuple(
                Mismatch(
                    m["subject"],
                    m["subject_kind"],
                    MismatchKind(m["kind"]),
                    m["detail"],
                )
                for m in d["mismatches"]
            ),
        )


def pattern_subject(source: str, relationship: str, target: str) -> str:
    return f"({source})-[{relationship}]->({target})"


def assess_conformance(declared: Ontology, observed: ObservedSchema) -> Conformance:
    """Compare element by element. Elements are node types, relationship types, their
    properties and endpoint patterns, taken from both sides: every declared one and every
    observed one that is not declared.

    `score` = conforming elements / all elements, where an element conforms when it is
    both declared and observed and has no mismatch. Every element of an absent or
    undeclared type is reported on its own (an absent `Ticket` also makes
    `Ticket.opened_at` absent), so the score and the breakdown always agree.
    Order: node types, then relationship types, each by label with its properties
    (by name) right after it; then patterns, sorted."""
    checks = _Checks()
    _check_concepts(checks, "node_type", declared.node_types, observed.node_types)
    _check_concepts(
        checks,
        "relationship_type",
        declared.relationship_types,
        observed.relationship_types,
    )
    _check_patterns(checks, declared, observed)
    return checks.result()


class _Checks:
    def __init__(self) -> None:
        self._conforms: dict[tuple[str, str], bool] = {}
        self._mismatches: list[Mismatch] = []

    def record(self, subject: str, kind: SubjectKind, found: list[Mismatch]) -> None:
        self._conforms[
            (kind, subject)
        ] = not found  # a node and a relationship may share a label
        self._mismatches.extend(found)

    def presence(
        self, subject: str, kind: SubjectKind, is_declared: bool, is_observed: bool
    ) -> bool:
        """Record an absent/undeclared element; True when it is on both sides."""
        if not is_declared:
            self.record(
                subject, kind, [Mismatch(subject, kind, MismatchKind.UNDECLARED)]
            )
        elif not is_observed:
            self.record(subject, kind, [Mismatch(subject, kind, MismatchKind.ABSENT)])
        return is_declared and is_observed

    def result(self) -> Conformance:
        total = len(self._conforms)
        score = sum(self._conforms.values()) / total if total else 1.0
        return Conformance(score=score, mismatches=tuple(self._mismatches))


def _check_concepts(
    checks: _Checks,
    kind: SubjectKind,
    declared: tuple[NodeType, ...] | tuple[RelationshipType, ...],
    observed: tuple[ObservedNodeType, ...] | tuple[ObservedRelationshipType, ...],
) -> None:
    declared_by_label = {c.label: c for c in declared}
    observed_by_label = {o.label: o for o in observed}
    for label in sorted(declared_by_label.keys() | observed_by_label.keys()):
        d = declared_by_label.get(label)
        o = observed_by_label.get(label)
        if checks.presence(label, kind, d is not None, o is not None):
            checks.record(label, kind, [])
        declared_props = {p.name: p for p in (d.properties if d else ())}
        observed_props = {p.name: p for p in (o.properties if o else ())}
        for name in sorted(declared_props.keys() | observed_props.keys()):
            subject = f"{label}.{name}"
            dp, op = declared_props.get(name), observed_props.get(name)
            if checks.presence(subject, "property", dp is not None, op is not None):
                checks.record(
                    subject, "property", _property_mismatches(subject, label, dp, op)
                )


def _property_mismatches(
    subject: str, owner: str, declared: Property, observed: ObservedProperty
) -> list[Mismatch]:
    found = []
    if declared.required and observed.fill_rate < 1.0:
        found.append(
            Mismatch(
                subject,
                "property",
                MismatchKind.REQUIRED_MISSING,
                f"required, but filled on {observed.fill_rate:.0%} of {owner}",
            )
        )
    conforming_types = {declared.type} | {
        old for old, new in WIDENING_TYPE_CHANGES if new == declared.type
    }
    if not set(observed.types) <= conforming_types:
        found.append(
            Mismatch(
                subject,
                "property",
                MismatchKind.TYPE_MISMATCH,
                f"declared {declared.type}, observed {', '.join(observed.types)}",
            )
        )
    return found


def _check_patterns(
    checks: _Checks, declared: Ontology, observed: ObservedSchema
) -> None:
    declared_patterns = {
        (p.source, p.relationship, p.target) for p in declared.patterns
    }
    observed_patterns = {
        (p.source, p.relationship, p.target) for p in observed.patterns
    }
    for key in sorted(declared_patterns | observed_patterns):
        subject = pattern_subject(*key)
        if checks.presence(
            subject, "pattern", key in declared_patterns, key in observed_patterns
        ):
            checks.record(subject, "pattern", [])


# --- Candidates ---------------------------------------------------------------------


def candidate_ontology(declared: Ontology, observed: ObservedSchema) -> Ontology | None:
    """The Declared Ontology plus the newly observed Concepts, or None when the Observed
    Schema introduces none.

    New Concepts are undeclared node types, relationship types and properties (also on
    declared types). New properties are optional and typed from the observation, so the
    Candidate is an additive change of the Declared Ontology. Observed patterns are added
    only when they involve a new node or relationship type: an undeclared pattern between
    declared Concepts is a pattern mismatch, not a new Concept, and is left out."""
    node_types, new_nodes, new_node_props = _extend(
        declared.node_types, observed.node_types, NodeType
    )
    relationship_types, new_rels, new_rel_props = _extend(
        declared.relationship_types, observed.relationship_types, RelationshipType
    )
    if not (new_nodes or new_rels or new_node_props or new_rel_props):
        return None
    patterns = set(declared.patterns) | {
        Pattern(p.source, p.relationship, p.target)
        for p in observed.patterns
        if {p.source, p.target} & new_nodes or p.relationship in new_rels
    }
    return Ontology(
        node_types=node_types,
        relationship_types=relationship_types,
        patterns=tuple(sorted(patterns)),
    )


def _extend(declared, observed, concept_type):
    """Declared Concepts with their undeclared observed properties added, plus the
    undeclared observed Concepts, sorted by label; also the new labels and whether any
    property was added to a declared Concept."""
    observed_by_label = {o.label: o for o in observed}
    declared_labels = {c.label for c in declared}
    extended = []
    added_properties = False
    for c in declared:
        o = observed_by_label.get(c.label)
        known = {p.name for p in c.properties}
        extra = tuple(
            _property(p) for p in (o.properties if o else ()) if p.name not in known
        )
        added_properties = added_properties or bool(extra)
        extended.append(
            replace(
                c, properties=tuple(sorted(c.properties + extra, key=lambda p: p.name))
            )
            if extra
            else c
        )
    new_labels = set(observed_by_label) - declared_labels
    for label in new_labels:
        props = observed_by_label[label].properties
        extended.append(
            concept_type(label=label, properties=tuple(_property(p) for p in props))
        )
    return tuple(sorted(extended, key=lambda c: c.label)), new_labels, added_properties


def _property(observed: ObservedProperty) -> Property:
    """An optional property typed from the observation. Mixed INTEGER/FLOAT values widen
    to FLOAT; any other mix takes the first type name (alphabetically)."""
    types = set(observed.types)
    widened = {new for old, new in WIDENING_TYPE_CHANGES if {old, new} == types}
    return Property(name=observed.name, type=next(iter(widened), observed.types[0]))
