"""Ontology Diff engine: a pure function of two Ontologies -> classified Concept changes.

Concepts are matched by label (attributes by `<owner>.<name>`), never by guessing:
an undeclared rename is a removal plus an addition.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum

from stetiq.ontology.canonical import Deprecatable, Documented
from stetiq.ontology.model import (
    ConceptKind,
    NodeType,
    Ontology,
    Pattern,
    Property,
    RelationshipType,
    Vocabulary,
    is_deprecated,
)


class ChangeKind(StrEnum):
    ADDED = "added"
    REMOVED = "removed"
    CHANGED = "changed"
    DEPRECATED = "deprecated"


class Classification(StrEnum):
    """Consumer impact, ordered from least to most severe. A cosmetic change touches only
    documentation (a Definition, Alternative Labels or a Deprecation reason), never what
    data conforms."""

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
    `<owner label>.<property name>` for an attribute, a Vocabulary's label, or
    `<Vocabulary label>.<value label>` for a Vocabulary Value. `detail` says what changed in
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
    # A Vocabulary change's Vocabulary, and the Vocabulary Value it concerns, if any.
    vocabulary: str | None = None
    value: str | None = None


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


# A Change's detail names its Concept kind in GLOSSARY.md's words, not the wire's.
_KIND_NAMES: dict[str, str] = {
    "node_type": "Class",
    "relationship_type": "Relation",
    "property": "Attribute",
    "vocabulary": "Vocabulary",
}


def diff_ontologies(base: Ontology, target: Ontology) -> OntologyDiff:
    """Every Concept change from `base` to `target`, each classified."""
    changes: list[Change] = []
    changes += _diff_concepts("node_type", base.node_types, target.node_types, base, target)
    changes += _diff_concepts(
        "relationship_type", base.relationship_types, target.relationship_types, base, target
    )
    changes += _diff_constraints(base, target)
    changes += _diff_vocabularies(base.vocabularies, target.vocabularies)
    return OntologyDiff(tuple(changes))


def _diff_vocabularies(
    base: tuple[Vocabulary, ...], target: tuple[Vocabulary, ...]
) -> list[Change]:
    """Adding or removing a Vocabulary is additive: only a binding, diffed on its attribute,
    makes data conform to it, and a removed one can no longer be bound. Within a kept one,
    adding a value is additive and removing one breaking."""
    old = {v.label: v for v in base}
    new = {v.label: v for v in target}
    changes: list[Change] = []
    for label in sorted(old.keys() | new.keys()):
        item = _VocabularyItem(label)
        if label not in old:
            changes.append(item.change(ChangeKind.ADDED, Classification.ADDITIVE, "added"))
        elif label not in new:
            changes.append(item.change(ChangeKind.REMOVED, Classification.ADDITIVE, "removed"))
        else:
            changes += [
                item.change(ChangeKind.CHANGED, Classification.COSMETIC, detail, prefix=False)
                for detail in _documentation_changes(old[label], new[label])
            ]
            changes += _diff_vocabulary_values(label, old[label], new[label])
    return changes


def _diff_vocabulary_values(
    label: str, old_vocabulary: Vocabulary, new_vocabulary: Vocabulary
) -> list[Change]:
    old = {v.label: v for v in old_vocabulary.values}
    new = {v.label: v for v in new_vocabulary.values}
    changes: list[Change] = []
    for value in sorted(old.keys() | new.keys()):
        item = _VocabularyItem(label, value)
        if value not in old:
            changes.append(item.change(ChangeKind.ADDED, Classification.ADDITIVE, "added"))
        elif value not in new:
            changes.append(item.change(ChangeKind.REMOVED, Classification.BREAKING, "removed"))
        else:
            changes += [
                item.change(change_kind, classification, detail, prefix=False)
                for change_kind, classification, detail in _deprecation_changes(
                    old[value], new[value]
                )
            ]
            changes += [
                item.change(ChangeKind.CHANGED, Classification.COSMETIC, detail, prefix=False)
                for detail in _documentation_changes(old[value], new[value])
            ]
    return changes


@dataclass(frozen=True)
class _VocabularyItem:
    """Vocabulary `vocabulary` itself, or its Vocabulary Value `value`."""

    vocabulary: str
    value: str | None = None

    @property
    def concept(self) -> str:
        return self.vocabulary if self.value is None else f"{self.vocabulary}.{self.value}"

    def change(
        self, kind: ChangeKind, classification: Classification, detail: str, prefix: bool = True
    ) -> Change:
        """With `prefix`, `detail` follows the item's name (`Vocabulary Value Status.done removed`);
        a change to an item that is still there says only what changed."""
        if prefix:
            noun = "Vocabulary" if self.value is None else "Vocabulary Value"
            detail = f"{noun} {self.concept} {detail}"
        return Change(
            self.concept,
            "vocabulary",
            kind,
            classification,
            detail,
            vocabulary=self.vocabulary,
            value=self.value,
        )


def _diff_constraints(base: Ontology, target: Ontology) -> list[Change]:
    """A new constraint may reject existing data (breaking); dropping one only relaxes (additive)."""
    old, new = set(base.constraints), set(target.constraints)
    changes = [
        _Attribute(c.node_type, "node_type", c.property_name).change(
            ChangeKind.CHANGED, Classification.BREAKING, f"{c.type} constraint added"
        )
        for c in sorted(new - old)
    ]
    changes += [
        _Attribute(c.node_type, "node_type", c.property_name).change(
            ChangeKind.CHANGED, Classification.ADDITIVE, f"{c.type} constraint removed"
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
            changes += [
                Change(label, kind, ChangeKind.CHANGED, Classification.COSMETIC, detail)
                for detail in _documentation_changes(old[label], new[label])
            ]
            changes += _diff_properties(kind, old[label], new[label])
            old_concept, new_concept = old[label], new[label]
            if isinstance(old_concept, NodeType) and isinstance(new_concept, NodeType):
                changes += _diff_parent(old_concept, new_concept)
            if kind == "relationship_type":
                changes += _diff_patterns(label, base_ontology, target_ontology)
    return changes


def _documentation_changes(old: Documented, new: Documented) -> list[str]:
    """What changed in a Concept's documentation, each cosmetic: it never changes what data conforms."""
    details = []
    if old.definition != new.definition:
        details.append("definition changed")
    if old.alternative_labels != new.alternative_labels:
        details.append("alternative labels changed")
    return details


def _deprecation_changes(
    old: Deprecatable, new: Deprecatable
) -> list[tuple[ChangeKind, Classification, str]]:
    """Deprecating (incl. a rename declared via `replacedBy`) is deprecating; undeprecating is
    additive; rewording only the Deprecation reason is cosmetic.

    Like every change to a Concept that is still there, the detail says what changed without
    repeating the Concept, which the change names beside it."""
    replacement = f"; replaced by {new.replaced_by}" if new.replaced_by else ""
    if is_deprecated(new) and not is_deprecated(old):
        return [(ChangeKind.DEPRECATED, Classification.DEPRECATING, f"deprecated{replacement}")]
    if is_deprecated(old) and not is_deprecated(new):
        return [(ChangeKind.CHANGED, Classification.ADDITIVE, "no longer deprecated")]
    changes = []
    if old.replaced_by != new.replaced_by:
        changes.append(
            (
                ChangeKind.DEPRECATED,
                Classification.DEPRECATING,
                f"replacement changed {old.replaced_by or '(none)'} -> {new.replaced_by or '(none)'}",
            )
        )
    if old.deprecation_reason != new.deprecation_reason:
        changes.append((ChangeKind.CHANGED, Classification.COSMETIC, "deprecation reason changed"))
    return changes


def _diff_deprecation(
    kind: ConceptKind, old: NodeType | RelationshipType, new: NodeType | RelationshipType
) -> list[Change]:
    return [
        Change(new.label, kind, change_kind, classification, detail)
        for change_kind, classification, detail in _deprecation_changes(old, new)
    ]


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
    # Patterns compare by endpoints only, so look each kept one up on both sides.
    old_by_endpoints, new_by_endpoints = {p: p for p in old}, {p: p for p in new}
    for p in sorted(old & new):
        changes += _diff_cardinality(label, old_by_endpoints[p], new_by_endpoints[p])
    return changes


def _diff_cardinality(label: str, old: Pattern, new: Pattern) -> list[Change]:
    """Per bound: adding or tightening one may reject existing data (breaking); loosening or
    removing one only relaxes (additive). A min tightens upwards, a max downwards."""
    changes: list[Change] = []
    for direction in ("out", "in"):
        for end in ("min", "max"):
            before = getattr(old, f"{end}_{direction}")
            after = getattr(new, f"{end}_{direction}")
            if before == after:
                continue
            if after is None:
                tightened = False
            elif before is None:
                tightened = True
            else:
                tightened = after > before if end == "min" else after < before
            changes.append(
                Change(
                    label,
                    "relationship_type",
                    ChangeKind.CHANGED,
                    Classification.BREAKING if tightened else Classification.ADDITIVE,
                    f"{new} {direction} {end} {_bound(before)} -> {_bound(after)}",
                    pattern=new.endpoints,
                )
            )
    return changes


def _bound(value: int | None) -> str:
    return "(none)" if value is None else str(value)


# Property type changes that only widen the set of accepted values (every old value
# is still valid). Any other type change narrows or reinterprets values: breaking.
WIDENING_TYPE_CHANGES: frozenset[tuple[str, str]] = frozenset({("INTEGER", "FLOAT")})


@dataclass(frozen=True)
class _Attribute:
    """Attribute `name` of the node or relationship type `owner`."""

    owner: str
    owner_kind: ConceptKind
    name: str

    @property
    def concept(self) -> str:
        return f"{self.owner}.{self.name}"

    def change(
        self,
        kind: ChangeKind,
        classification: Classification,
        detail: str,
        required: bool | None = None,
    ) -> Change:
        return Change(
            self.concept,
            "property",
            kind,
            classification,
            detail,
            owner=self.owner,
            owner_kind=self.owner_kind,
            attribute=self.name,
            required=required,
        )


def _diff_properties(
    owner_kind: ConceptKind,
    old_owner: NodeType | RelationshipType,
    new_owner: NodeType | RelationshipType,
) -> list[Change]:
    old = {p.name: p for p in old_owner.properties}
    new = {p.name: p for p in new_owner.properties}
    changes: list[Change] = []
    for name in sorted(old.keys() | new.keys()):
        attribute = _Attribute(old_owner.label, owner_kind, name)
        if name not in old:
            # Existing data lacks a newly required property, so it no longer conforms.
            required = new[name].required
            changes.append(
                attribute.change(
                    ChangeKind.ADDED,
                    Classification.BREAKING if required else Classification.ADDITIVE,
                    f"{'required' if required else 'optional'} Attribute {attribute.concept} added",
                    required=required,
                )
            )
        elif name not in new:
            changes.append(
                attribute.change(
                    ChangeKind.REMOVED,
                    Classification.BREAKING,
                    f"Attribute {attribute.concept} removed",
                )
            )
        else:
            changes += _diff_property(attribute, old[name], new[name])
    return changes


def _diff_property(attribute: _Attribute, old: Property, new: Property) -> list[Change]:
    def change(classification: Classification, detail: str) -> Change:
        return attribute.change(ChangeKind.CHANGED, classification, detail)

    changes = [
        attribute.change(change_kind, classification, detail)
        for change_kind, classification, detail in _deprecation_changes(old, new)
    ]
    changes += [
        change(Classification.COSMETIC, detail) for detail in _documentation_changes(old, new)
    ]
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
    changes += _diff_binding(change, old.vocabulary, new.vocabulary)
    return changes


def _diff_binding(
    change: Callable[[Classification, str], Change], old: str | None, new: str | None
) -> list[Change]:
    """Binding an attribute to a Vocabulary (or to another one) may reject existing values
    (breaking); unbinding only relaxes (additive)."""
    if old == new:
        return []
    if new is None:
        return [change(Classification.ADDITIVE, f"no longer bound to Vocabulary {old}")]
    if old is None:
        return [change(Classification.BREAKING, f"bound to Vocabulary {new}")]
    return [change(Classification.BREAKING, f"Vocabulary {old} -> {new}")]


# --- Added Concepts ------------------------------------------------------------------


@dataclass(frozen=True)
class AddedConcept:
    """A Concept the Ontology Diff adds; `owner` is the (kind, identity) of the added
    Class or Relation an Attribute belongs to, or of the declared one it was added to."""

    kind: ConceptKind
    identity: str
    owner: tuple[ConceptKind, str] | None = None

    @property
    def key(self) -> tuple[ConceptKind, str]:
        return (self.kind, self.identity)


def added_concepts(base: Ontology, target: Ontology) -> list[AddedConcept]:
    """Every Concept the diff from `base` to `target` adds: added Classes and Relations,
    each followed by its own Attributes (owned by it), and Attributes added to a Class or
    Relation `base` has. Vocabularies and their Values are not Concepts and are left out."""
    owners = {
        **{("node_type", n.label): n for n in target.node_types},
        **{("relationship_type", r.label): r for r in target.relationship_types},
    }
    added: list[AddedConcept] = []
    for change in diff_ontologies(base, target).changes:
        if change.kind != ChangeKind.ADDED:
            continue
        if change.concept_kind in ("node_type", "relationship_type"):
            concept = AddedConcept(change.concept_kind, change.concept)
            added.append(concept)
            added += [
                AddedConcept("property", f"{change.concept}.{p.name}", concept.key)
                for p in owners[concept.key].properties
            ]
        elif change.concept_kind == "property" and change.owner and change.owner_kind:
            added.append(
                AddedConcept("property", change.concept, (change.owner_kind, change.owner))
            )
    return added
