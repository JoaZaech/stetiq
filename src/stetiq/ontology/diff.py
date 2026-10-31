"""Ontology Diff engine: a pure function of two Ontologies -> classified Concept changes.

Concepts are matched by label (attributes by `<owner>.<name>`), never by guessing:
an undeclared rename is a removal plus an addition.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from stetiq.ontology.model import (
    ConceptKind,
    NodeType,
    Ontology,
    Pattern,
    Property,
    RelationshipType,
)


class ChangeKind(StrEnum):
    ADDED = "added"
    REMOVED = "removed"
    CHANGED = "changed"
    DEPRECATED = "deprecated"


class Classification(StrEnum):
    """Consumer impact, ordered from least to most severe. A cosmetic change touches only
    documentation (a description), never what data conforms."""

    COSMETIC = "cosmetic"
    ADDITIVE = "additive"
    DEPRECATING = "deprecating"
    BREAKING = "breaking"

    @property
    def severity(self) -> int:
        return list(Classification).index(self)


@dataclass(frozen=True)
class Change:
    """One change to one Concept.

    `concept` is the Concept's identity: a node/relationship type label, or
    `<owner label>.<property name>` for an attribute. `detail` says what changed in
    words, for people only; the fields below state what code needs to know, so no code
    has to read `detail`.
    """

    concept: str
    concept_kind: ConceptKind
    kind: ChangeKind
    classification: Classification
    detail: str
    # An attribute change's owner (a node or relationship type) and the attribute's name.
    owner: str | None = None
    owner_kind: ConceptKind | None = None
    attribute: str | None = None
    # Whether an added attribute is required; None for any other change.
    required: bool | None = None
    # The endpoint Pattern an endpoint change adds or removes.
    pattern: Pattern | None = None


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

    @property
    def cosmetic(self) -> tuple[Change, ...]:
        return self.by_classification(Classification.COSMETIC)


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
    changes += _diff_constraints(base, target)
    return OntologyDiff(tuple(changes))


def _diff_constraints(base: Ontology, target: Ontology) -> list[Change]:
    """A new constraint may reject existing data (breaking); dropping one only relaxes (additive)."""
    old, new = set(base.constraints), set(target.constraints)
    changes = [
        _attribute_change(
            c.node_type,
            "node_type",
            c.property_name,
            ChangeKind.CHANGED,
            Classification.BREAKING,
            f"{c.type} constraint added",
        )
        for c in sorted(new - old)
    ]
    changes += [
        _attribute_change(
            c.node_type,
            "node_type",
            c.property_name,
            ChangeKind.CHANGED,
            Classification.ADDITIVE,
            f"{c.type} constraint removed",
        )
        for c in sorted(old - new)
    ]
    return changes


def _diff_parent(old: NodeType, new: NodeType) -> list[Change]:
    """Giving a root a parent only adds a supertype (additive); moving or removing one
    drops it from queries over the old supertype (breaking)."""
    if old.parent == new.parent:
        return []
    classification = Classification.ADDITIVE if old.parent is None else Classification.BREAKING
    detail = f"parent {old.parent or '(none)'} -> {new.parent or '(none)'}"
    return [Change(new.label, "node_type", ChangeKind.CHANGED, classification, detail)]


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
            changes.append(
                Change(
                    label, kind, ChangeKind.ADDED, Classification.ADDITIVE, f"{name} {label} added"
                )
            )
        elif label not in new:
            changes.append(
                Change(
                    label,
                    kind,
                    ChangeKind.REMOVED,
                    Classification.BREAKING,
                    f"{name} {label} removed",
                )
            )
        else:
            changes += _diff_deprecation(kind, old[label], new[label])
            if old[label].description != new[label].description:
                changes.append(
                    Change(
                        label,
                        kind,
                        ChangeKind.CHANGED,
                        Classification.COSMETIC,
                        "description changed",
                    )
                )
            changes += _diff_properties(kind, old[label], new[label])
            old_concept, new_concept = old[label], new[label]
            if isinstance(old_concept, NodeType) and isinstance(new_concept, NodeType):
                changes += _diff_parent(old_concept, new_concept)
            if kind == "relationship_type":
                changes += _diff_patterns(label, base_ontology, target_ontology)
    return changes


def _is_deprecated(c: NodeType | RelationshipType) -> bool:
    # Declaring a replacement implies the Concept is on its way out.
    return c.deprecated or c.replaced_by is not None


def _diff_deprecation(
    kind: ConceptKind, old: NodeType | RelationshipType, new: NodeType | RelationshipType
) -> list[Change]:
    """Deprecating (incl. a rename declared via `replacedBy`) is deprecating; undeprecating is additive.

    Like every change to a Concept that is still there, the detail says what changed without
    repeating the Concept, which the change names beside it."""
    label = new.label
    replacement = f"; replaced by {new.replaced_by}" if new.replaced_by else ""
    if _is_deprecated(new) and not _is_deprecated(old):
        return [
            Change(
                label,
                kind,
                ChangeKind.DEPRECATED,
                Classification.DEPRECATING,
                f"deprecated{replacement}",
            )
        ]
    if _is_deprecated(old) and not _is_deprecated(new):
        return [
            Change(
                label,
                kind,
                ChangeKind.CHANGED,
                Classification.ADDITIVE,
                "no longer deprecated",
            )
        ]
    if old.replaced_by != new.replaced_by:
        return [
            Change(
                label,
                kind,
                ChangeKind.DEPRECATED,
                Classification.DEPRECATING,
                f"replacement changed {old.replaced_by or '(none)'} -> {new.replaced_by or '(none)'}",
            )
        ]
    return []


def _patterns(ontology: Ontology, relationship: str) -> set[Pattern]:
    return {p for p in ontology.patterns if p.relationship == relationship}


def _diff_patterns(label: str, base: Ontology, target: Ontology) -> list[Change]:
    """Endpoint patterns: allowing more is additive, allowing less (narrowing) is breaking."""
    old, new = _patterns(base, label), _patterns(target, label)
    changes = [
        Change(
            label,
            "relationship_type",
            ChangeKind.CHANGED,
            Classification.ADDITIVE,
            f"endpoint pattern {p} added",
            pattern=p,
        )
        for p in sorted(new - old)
    ]
    changes += [
        Change(
            label,
            "relationship_type",
            ChangeKind.CHANGED,
            Classification.BREAKING,
            f"endpoint pattern {p} removed",
            pattern=p,
        )
        for p in sorted(old - new)
    ]
    return changes


# Property type changes that only widen the set of accepted values (every old value
# is still valid). Any other type change narrows or reinterprets values: breaking.
WIDENING_TYPE_CHANGES: frozenset[tuple[str, str]] = frozenset({("INTEGER", "FLOAT")})


def _attribute_change(
    owner: str,
    owner_kind: ConceptKind,
    name: str,
    kind: ChangeKind,
    classification: Classification,
    detail: str,
    required: bool | None = None,
) -> Change:
    """A change to attribute `name` of the node or relationship type `owner`."""
    return Change(
        f"{owner}.{name}",
        "property",
        kind,
        classification,
        detail,
        owner=owner,
        owner_kind=owner_kind,
        attribute=name,
        required=required,
    )


def _diff_properties(
    owner_kind: ConceptKind,
    old_owner: NodeType | RelationshipType,
    new_owner: NodeType | RelationshipType,
) -> list[Change]:
    old = {p.name: p for p in old_owner.properties}
    new = {p.name: p for p in new_owner.properties}
    owner = old_owner.label
    changes: list[Change] = []
    for name in sorted(old.keys() | new.keys()):
        concept = f"{owner}.{name}"
        if name not in old:
            # Existing data lacks a newly required property, so it no longer conforms.
            required = new[name].required
            changes.append(
                _attribute_change(
                    owner,
                    owner_kind,
                    name,
                    ChangeKind.ADDED,
                    Classification.BREAKING if required else Classification.ADDITIVE,
                    f"{'required' if required else 'optional'} property {concept} added",
                    required=required,
                )
            )
        elif name not in new:
            changes.append(
                _attribute_change(
                    owner,
                    owner_kind,
                    name,
                    ChangeKind.REMOVED,
                    Classification.BREAKING,
                    f"property {concept} removed",
                )
            )
        else:
            changes += _diff_property(owner, owner_kind, name, old[name], new[name])
    return changes


def _diff_property(
    owner: str, owner_kind: ConceptKind, name: str, old: Property, new: Property
) -> list[Change]:
    def change(classification: Classification, detail: str) -> Change:
        return _attribute_change(
            owner, owner_kind, name, ChangeKind.CHANGED, classification, detail
        )

    changes: list[Change] = []
    if old.description != new.description:
        changes.append(change(Classification.COSMETIC, "description changed"))
    if old.type != new.type:
        widening = (old.type, new.type) in WIDENING_TYPE_CHANGES
        changes.append(
            change(
                Classification.ADDITIVE if widening else Classification.BREAKING,
                f"type {old.type} -> {new.type} ({'widened' if widening else 'narrowed'})",
            )
        )
    if old.required != new.required:
        changes.append(
            change(
                Classification.BREAKING if new.required else Classification.ADDITIVE,
                "now required" if new.required else "now optional",
            )
        )
    return changes
