"""Ontology Diff engine: a pure function of two Ontologies -> classified Concept changes.

Concepts are matched by label (attributes by `<owner>.<name>`), never by guessing:
an undeclared rename is a removal plus an addition.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Literal

from stetiq.ontology.model import NodeType, Ontology, Pattern, Property, RelationshipType


class ChangeKind(StrEnum):
    ADDED = "added"
    REMOVED = "removed"
    CHANGED = "changed"
    DEPRECATED = "deprecated"


class Classification(StrEnum):
    """Consumer impact, ordered from least to most severe."""

    ADDITIVE = "additive"
    DEPRECATING = "deprecating"
    BREAKING = "breaking"

    @property
    def severity(self) -> int:
        return list(Classification).index(self)


ConceptKind = Literal["node_type", "relationship_type", "property"]


@dataclass(frozen=True)
class Change:
    """One change to one Concept.

    `concept` is the Concept's identity: a node/relationship type label, or
    `<owner label>.<property name>` for an attribute.
    """

    concept: str
    concept_kind: ConceptKind
    kind: ChangeKind
    classification: Classification
    detail: str


@dataclass(frozen=True)
class OntologyDiff:
    changes: tuple[Change, ...] = ()

    @property
    def classification(self) -> Classification | None:
        """The most severe classification among the changes; None when nothing changed."""
        if not self.changes:
            return None
        return max((c.classification for c in self.changes), key=lambda c: c.severity)

    @property
    def is_breaking(self) -> bool:
        return self.classification is Classification.BREAKING

    def by_classification(self, classification: Classification | str) -> tuple[Change, ...]:
        return tuple(c for c in self.changes if c.classification == classification)

    @property
    def breaking(self) -> tuple[Change, ...]:
        return self.by_classification(Classification.BREAKING)

    @property
    def deprecating(self) -> tuple[Change, ...]:
        return self.by_classification(Classification.DEPRECATING)

    @property
    def additive(self) -> tuple[Change, ...]:
        return self.by_classification(Classification.ADDITIVE)


_KIND_NAMES: dict[str, str] = {
    "node_type": "node type",
    "relationship_type": "relationship type",
    "property": "property",
}


def diff_ontologies(base: Ontology, target: Ontology) -> OntologyDiff:
    """Every Concept change from `base` to `target`, each classified."""
    changes: list[Change] = []
    changes += _diff_concepts("node_type", base.node_types, target.node_types, base, target)
    changes += _diff_concepts(
        "relationship_type", base.relationship_types, target.relationship_types, base, target
    )
    return OntologyDiff(tuple(changes))


def _diff_concepts(
    kind: ConceptKind,
    base: tuple[NodeType | RelationshipType, ...],
    target: tuple[NodeType | RelationshipType, ...],
    base_ontology: Ontology,
    target_ontology: Ontology,
) -> list[Change]:
    old = {c.label: c for c in base}
    new = {c.label: c for c in target}
    name = _KIND_NAMES[kind]
    changes: list[Change] = []
    for label in sorted(old.keys() | new.keys()):
        if label not in old:
            changes.append(Change(label, kind, ChangeKind.ADDED, Classification.ADDITIVE, f"{name} {label} added"))
        elif label not in new:
            changes.append(Change(label, kind, ChangeKind.REMOVED, Classification.BREAKING, f"{name} {label} removed"))
        else:
            changes += _diff_deprecation(kind, old[label], new[label])
            if old[label].description != new[label].description:
                changes.append(Change(label, kind, ChangeKind.CHANGED, Classification.ADDITIVE, "description changed"))
            changes += _diff_properties(old[label], new[label])
            if kind == "relationship_type":
                changes += _diff_patterns(label, base_ontology, target_ontology)
    return changes


def _is_deprecated(c: NodeType | RelationshipType) -> bool:
    # Declaring a replacement implies the Concept is on its way out.
    return c.deprecated or c.replaced_by is not None


def _diff_deprecation(kind: ConceptKind, old: NodeType | RelationshipType, new: NodeType | RelationshipType) -> list[Change]:
    """Deprecating (incl. a rename declared via `replacedBy`) is deprecating; undeprecating is additive."""
    label = new.label
    replacement = f"; replaced by {new.replaced_by}" if new.replaced_by else ""
    if _is_deprecated(new) and not _is_deprecated(old):
        return [Change(label, kind, ChangeKind.DEPRECATED, Classification.DEPRECATING, f"{_KIND_NAMES[kind]} {label} deprecated{replacement}")]
    if _is_deprecated(old) and not _is_deprecated(new):
        return [Change(label, kind, ChangeKind.CHANGED, Classification.ADDITIVE, f"{_KIND_NAMES[kind]} {label} no longer deprecated")]
    if old.replaced_by != new.replaced_by:
        return [
            Change(
                label,
                kind,
                ChangeKind.DEPRECATED,
                Classification.DEPRECATING,
                f"{_KIND_NAMES[kind]} {label} replacement changed {old.replaced_by or '(none)'} -> {new.replaced_by or '(none)'}",
            )
        ]
    return []


def _patterns(ontology: Ontology, relationship: str) -> set[Pattern]:
    return {p for p in ontology.patterns if p.relationship == relationship}


def _fmt(p: Pattern) -> str:
    return f"({p.source})-[{p.relationship}]->({p.target})"


def _diff_patterns(label: str, base: Ontology, target: Ontology) -> list[Change]:
    """Endpoint patterns: allowing more is additive, allowing less (narrowing) is breaking."""
    old, new = _patterns(base, label), _patterns(target, label)
    changes = [
        Change(label, "relationship_type", ChangeKind.CHANGED, Classification.ADDITIVE, f"endpoint pattern {_fmt(p)} added")
        for p in sorted(new - old)
    ]
    changes += [
        Change(label, "relationship_type", ChangeKind.CHANGED, Classification.BREAKING, f"endpoint pattern {_fmt(p)} removed")
        for p in sorted(old - new)
    ]
    return changes


# Property type changes that only widen the set of accepted values (every old value
# is still valid). Any other type change narrows or reinterprets values: breaking.
WIDENING_TYPE_CHANGES: frozenset[tuple[str, str]] = frozenset({("INTEGER", "FLOAT")})


def _diff_properties(old_owner: NodeType | RelationshipType, new_owner: NodeType | RelationshipType) -> list[Change]:
    old = {p.name: p for p in old_owner.properties}
    new = {p.name: p for p in new_owner.properties}
    changes: list[Change] = []
    for name in sorted(old.keys() | new.keys()):
        concept = f"{old_owner.label}.{name}"
        if name not in old:
            # Existing data lacks a newly required property, so it no longer conforms.
            required = new[name].required
            changes.append(
                Change(
                    concept,
                    "property",
                    ChangeKind.ADDED,
                    Classification.BREAKING if required else Classification.ADDITIVE,
                    f"{'required' if required else 'optional'} property {concept} added",
                )
            )
        elif name not in new:
            changes.append(
                Change(concept, "property", ChangeKind.REMOVED, Classification.BREAKING, f"property {concept} removed")
            )
        else:
            changes += _diff_property(concept, old[name], new[name])
    return changes


def _diff_property(concept: str, old: Property, new: Property) -> list[Change]:
    changes: list[Change] = []
    if old.description != new.description:
        changes.append(Change(concept, "property", ChangeKind.CHANGED, Classification.ADDITIVE, "description changed"))
    if old.type != new.type:
        widening = (old.type, new.type) in WIDENING_TYPE_CHANGES
        changes.append(
            Change(
                concept,
                "property",
                ChangeKind.CHANGED,
                Classification.ADDITIVE if widening else Classification.BREAKING,
                f"type {old.type} -> {new.type} ({'widened' if widening else 'narrowed'})",
            )
        )
    if old.required != new.required:
        changes.append(
            Change(
                concept,
                "property",
                ChangeKind.CHANGED,
                Classification.BREAKING if new.required else Classification.ADDITIVE,
                "now required" if new.required else "now optional",
            )
        )
    return changes
