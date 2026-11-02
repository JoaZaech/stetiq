"""Conformance engine: pure function of (Declared Ontology, Observed Schema) -> score + breakdown.

No I/O. `assess_conformance` scores how well an Observed Schema matches its Declared
Ontology and lists every mismatch; `candidate_ontology` builds the Declared Ontology
extended with the newly observed Concepts and Vocabulary Values (what an evolving Construction Run proposes
as a Candidate).
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
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
from stetiq.ontology.diff import WIDENING_TYPE_CHANGES, AddedConcept, added_concepts
from stetiq.ontology.model import ConceptKind, Vocabulary, VocabularyValue, is_deprecated

# What a mismatch is about. Concepts are node types, relationship types and properties
# (identity `Owner.property`, as in the Ontology Diff); patterns are endpoint patterns
# `(Source)-[REL]->(Target)`, which are not Concepts of their own.
MismatchSubjectKind = ConceptKind | Literal["pattern"]


class MismatchKind(StrEnum):
    ABSENT = "absent"  # declared, not observed
    UNDECLARED = "undeclared"  # observed, not declared
    TYPE_MISMATCH = "type_mismatch"  # an Attribute holds values of an undeclared type
    REQUIRED_MISSING = "required_missing"  # a required Attribute is not set everywhere
    # an endpoint pattern's observed out- or in-degree is outside its declared cardinality
    CARDINALITY_VIOLATION = "cardinality_violation"
    # a Vocabulary-bound Attribute holds a value its Vocabulary does not have (one per value)
    VALUE_OUTSIDE_VOCABULARY = "value_outside_vocabulary"
    # a Vocabulary-bound Attribute holds a deprecated value: reported, but it conforms
    DEPRECATED_VALUE = "deprecated_value"


@dataclass(frozen=True)
class Mismatch:
    subject: str
    subject_kind: MismatchSubjectKind
    kind: MismatchKind
    detail: str = ""
    # For a value mismatch: the observed value and how many nodes or relationships hold it.
    value: str | None = None
    count: int | None = None
    # The Violation Rate: the share of owner nodes or relationships failing this check, for
    # `required_missing`, `value_outside_vocabulary` and `type_mismatch`. None when unknown
    # (a truncated value list, an Observed Schema without counts per type) or for a kind
    # without one.
    rate: float | None = None


@dataclass(frozen=True)
class Conformance:
    """`score` in [0, 1] is the share of checks that hold (see `assess_conformance`);
    `mismatches` lists every check that does not, in a deterministic order, plus the
    observed deprecated Vocabulary Values (`deprecated_value`), which conform."""

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
        """Endpoint patterns declared but not observed, observed but not declared, or
        observed with a degree outside their declared cardinality."""
        return tuple(m for m in self.mismatches if m.subject_kind == "pattern")

    @property
    def property_mismatches(self) -> tuple[Mismatch, ...]:
        """Properties both declared and observed whose observed values break the declaration,
        and observed deprecated Vocabulary Values (which conform)."""
        return tuple(
            m
            for m in self.mismatches
            if m.subject_kind == "property"
            and m.kind not in (MismatchKind.ABSENT, MismatchKind.UNDECLARED)
        )

    def _concepts(self, kind: MismatchKind) -> tuple[Mismatch, ...]:
        return tuple(m for m in self.mismatches if m.kind == kind and m.subject_kind != "pattern")

    def to_dict(self) -> dict[str, Any]:
        return {
            "score": self.score,
            "mismatches": [_mismatch_to_dict(m) for m in self.mismatches],
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
                    m.get("value"),
                    m.get("count"),
                    m.get("rate"),
                )
                for m in d["mismatches"]
            ),
        )


def _mismatch_to_dict(m: Mismatch) -> dict[str, Any]:
    d: dict[str, Any] = {
        "subject": m.subject,
        "subject_kind": m.subject_kind,
        "kind": str(m.kind),
        "detail": m.detail,
    }
    if m.value is not None:  # only value mismatches carry these
        d["value"] = m.value
        d["count"] = m.count
    if m.rate is not None:
        d["rate"] = m.rate
    return d


def assess_conformance(declared: Ontology, observed: ObservedSchema) -> Conformance:
    """Compare item by item. The checked items are node types, relationship types, their
    properties and endpoint patterns, taken from both sides: every declared one and every
    observed one that is not declared; plus each declared cardinality bound, and each
    Vocabulary-bound property whose values were observed (see `_check_values`).

    `score` = conforming items / all items, where an item conforms when it is
    both declared and observed and has no mismatch. Every item of an absent or
    undeclared type is reported on its own (an absent `Ticket` also makes
    `Ticket.opened_at` absent), so the score and the breakdown always agree.
    Order: node types, then relationship types, each by label with its properties
    (by name) right after it; then patterns, sorted, each followed by its cardinality
    violations (out, then in). A cardinality bound counts as one item; a direction with a
    failing bound is reported once. A bound property's value mismatches follow its own
    mismatches, in the observed values' order (most frequent first). A `deprecated_value`
    is reported but is not a failing check."""
    checks = _Checks()
    _check_concepts(
        checks,
        "node_type",
        declared.node_types,
        observed.node_types,
        _properties_of(declared),
        declared,
    )
    _check_concepts(
        checks,
        "relationship_type",
        declared.relationship_types,
        observed.relationship_types,
        _own_properties,
        declared,
    )
    _check_patterns(checks, declared, observed)
    return checks.result()


class _Checks:
    def __init__(self) -> None:
        self._conforms: dict[tuple[str, str], bool] = {}
        self._mismatches: list[Mismatch] = []

    def record(self, subject: str, kind: MismatchSubjectKind, found: list[Mismatch]) -> None:
        self._conforms[(kind, subject)] = not found  # a node and a relationship may share a label
        self._mismatches.extend(found)

    def item(self, key: str, conforms: bool) -> None:
        """Count one item that is reported, if at all, by a separate `report`."""
        self._conforms[("item", key)] = conforms

    def report(self, mismatch: Mismatch) -> None:
        self._mismatches.append(mismatch)

    def presence(
        self, subject: str, kind: MismatchSubjectKind, is_declared: bool, is_observed: bool
    ) -> bool:
        """Record an absent/undeclared item; True when it is on both sides."""
        if not is_declared:
            self.record(subject, kind, [Mismatch(subject, kind, MismatchKind.UNDECLARED)])
        elif not is_observed:
            self.record(subject, kind, [Mismatch(subject, kind, MismatchKind.ABSENT)])
        return is_declared and is_observed

    def result(self) -> Conformance:
        total = len(self._conforms)
        score = sum(self._conforms.values()) / total if total else 1.0
        return Conformance(score=score, mismatches=tuple(self._mismatches))


def _check_concepts(
    checks: _Checks,
    kind: MismatchSubjectKind,
    declared: tuple[NodeType, ...] | tuple[RelationshipType, ...],
    observed: tuple[ObservedNodeType, ...] | tuple[ObservedRelationshipType, ...],
    properties_of: PropertiesOf,
    ontology: Ontology,
) -> None:
    declared_by_label = {c.label: c for c in declared}
    observed_by_label = {o.label: o for o in observed}
    for label in sorted(declared_by_label.keys() | observed_by_label.keys()):
        d = declared_by_label.get(label)
        o = observed_by_label.get(label)
        if checks.presence(label, kind, d is not None, o is not None):
            checks.record(label, kind, [])
        declared_props = {p.name: p for p in (properties_of(d) if d else ())}
        observed_props = {p.name: p for p in (o.properties if o else ())}
        for name in sorted(declared_props.keys() | observed_props.keys()):
            subject = f"{label}.{name}"
            dp, op = declared_props.get(name), observed_props.get(name)
            present = checks.presence(subject, "property", dp is not None, op is not None)
            if present and dp is not None and op is not None:
                owner_count = o.count if o else 0
                checks.record(
                    subject, "property", _property_mismatches(subject, label, dp, op, owner_count)
                )
                _check_values(checks, subject, ontology, dp, op, owner_count)


# The properties declared for a Concept (own, and for node types inherited ones too).
PropertiesOf = Callable[[NodeType | RelationshipType], tuple[Property, ...]]


def _own_properties(concept: NodeType | RelationshipType) -> tuple[Property, ...]:
    return concept.properties


def _properties_of(declared: Ontology) -> PropertiesOf:
    """A node type's own properties plus those inherited from its ancestors (the
    nearest declaration of a name wins)."""
    nodes = {n.label: n for n in declared.node_types}

    def properties_of(concept: NodeType | RelationshipType) -> tuple[Property, ...]:
        props, names, seen = [], set(), set()
        current: NodeType | RelationshipType | None = concept
        while current is not None and current.label not in seen:
            seen.add(current.label)
            props += [p for p in current.properties if p.name not in names]
            names |= {p.name for p in current.properties}
            parent = getattr(current, "parent", None)
            current = nodes.get(parent) if parent else None
        return tuple(props)

    return properties_of


def _property_mismatches(
    subject: str, owner: str, declared: Property, observed: ObservedProperty, owner_count: int
) -> list[Mismatch]:
    found = []
    if declared.required and observed.fill_rate < 1.0:
        found.append(
            Mismatch(
                subject,
                "property",
                MismatchKind.REQUIRED_MISSING,
                f"required, but filled on {observed.fill_rate:.0%} of {owner}",
                rate=1.0 - observed.fill_rate,
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
                rate=_type_mismatch_rate(observed, conforming_types, owner_count),
            )
        )
    return found


def _type_mismatch_rate(
    observed: ObservedProperty, conforming_types: set[str], owner_count: int
) -> float | None:
    """The share of the `owner_count` owners holding a value of a non-conforming type (each
    owner holds at most one value). None when the Observed Schema did not count values per
    type (an older or third-party one)."""
    if observed.type_counts is None or owner_count <= 0:
        return None
    failing = sum(n for t, n in observed.type_counts if t not in conforming_types)
    return failing / owner_count


def _check_values(
    checks: _Checks,
    subject: str,
    ontology: Ontology,
    declared: Property,
    observed: ObservedProperty,
    owner_count: int,
) -> None:
    """A Vocabulary-bound Attribute whose values were observed is one item. Each observed
    value outside the Vocabulary fails it and is reported with its count and its share of
    the `owner_count` owners (the Violation Rate); a deprecated value is reported but
    conforms. Only listed values are checked: a truncated list (more distinct values than
    the cap) conforms when none of its values is outside the Vocabulary, and the Observed
    Schema's `truncated` flag says the list is incomplete, so its shares are unknown."""
    vocabulary = ontology.vocabulary(declared.vocabulary) if declared.vocabulary else None
    if vocabulary is None or observed.values is None:
        return
    values = {v.label: v for v in vocabulary.values}
    known_shares = not observed.values.truncated and owner_count > 0
    outside = False
    for c in observed.values.counts:
        value = values.get(c.value)
        times = f"{c.count} time{'s' if c.count != 1 else ''}"
        if value is None:
            outside = True
            checks.report(
                Mismatch(
                    subject,
                    "property",
                    MismatchKind.VALUE_OUTSIDE_VOCABULARY,
                    f"{c.value!r} observed {times}, not a value of {vocabulary.label}",
                    c.value,
                    c.count,
                    c.count / owner_count if known_shares else None,
                )
            )
        elif is_deprecated(value):
            replacement = f", replaced by {value.replaced_by!r}" if value.replaced_by else ""
            checks.report(
                Mismatch(
                    subject,
                    "property",
                    MismatchKind.DEPRECATED_VALUE,
                    f"{c.value!r} observed {times}, deprecated in {vocabulary.label}{replacement}",
                    c.value,
                    c.count,
                )
            )
    checks.item(f"vocabulary {subject}", not outside)


def _check_patterns(checks: _Checks, declared: Ontology, observed: ObservedSchema) -> None:
    declared_patterns = {p: p for p in declared.patterns}  # with their cardinality
    observed_patterns = {p.pattern for p in observed.patterns}
    for key in sorted(declared_patterns.keys() | observed_patterns):
        subject = str(key)
        if checks.presence(subject, "pattern", key in declared_patterns, key in observed_patterns):
            checks.record(subject, "pattern", [])
        if key in declared_patterns:
            _check_cardinality(checks, declared_patterns[key], observed)


def _check_cardinality(checks: _Checks, declared: Pattern, observed: ObservedSchema) -> None:
    """Each declared bound is one item. A direction with a failing bound is reported once,
    with the observed degree range against all of that direction's bounds. A pattern that
    is not observed gives every node of its type degree 0; with no such nodes either, its
    bounds hold."""
    seen = observed.pattern(declared.source, declared.relationship, declared.target)
    for direction, node_type in (("out", declared.source), ("in", declared.target)):
        low = getattr(declared, f"min_{direction}")
        high = getattr(declared, f"max_{direction}")
        if low is None and high is None:
            continue
        if seen is not None:
            degree = seen.out_degree if direction == "out" else seen.in_degree
            observed_range: tuple[int, int] | None = (degree.min, degree.max)
        else:
            nodes = observed.node_type(node_type)
            observed_range = (0, 0) if nodes is not None and nodes.count > 0 else None
        failing = False
        for end, bound in (("min", low), ("max", high)):
            if bound is None:
                continue
            holds = observed_range is None or (
                observed_range[0] >= bound if end == "min" else observed_range[1] <= bound
            )
            checks.item(f"cardinality {declared} {direction} {end}", holds)
            failing = failing or not holds
        if failing and observed_range is not None:
            bounds = ", ".join(
                f"{end} {bound}"
                for end, bound in (("min", low), ("max", high))
                if bound is not None
            )
            checks.report(
                Mismatch(
                    str(declared),
                    "pattern",
                    MismatchKind.CARDINALITY_VIOLATION,
                    f"{direction}-degree observed {observed_range[0]}..{observed_range[1]}, "
                    f"declared {bounds}",
                )
            )


# --- Candidates ---------------------------------------------------------------------


def candidate_ontology(declared: Ontology, observed: ObservedSchema) -> Ontology | None:
    """The Declared Ontology plus the newly observed Concepts, or None when the Observed
    Schema introduces none.

    New Concepts are undeclared node types, relationship types and properties (also on
    declared types). New properties are optional and typed from the observation, so the
    Candidate is an additive change of the Declared Ontology. Observed patterns are added
    only when they involve a new node or relationship type: an undeclared pattern between
    declared Concepts is a pattern mismatch, not a new Concept, and is left out.
    Observed values outside a bound Vocabulary are added to it as new Values, which is
    additive too."""
    node_types, new_nodes, new_node_props = _extend(
        declared.node_types, observed.node_types, NodeType, _properties_of(declared)
    )
    relationship_types, new_rels, new_rel_props = _extend(
        declared.relationship_types,
        observed.relationship_types,
        RelationshipType,
        _own_properties,
    )
    vocabularies = _extend_vocabularies(declared, observed)
    if not (new_nodes or new_rels or new_node_props or new_rel_props) and (
        vocabularies == declared.vocabularies
    ):
        return None
    # The declared patterns themselves (not their observed equals), so their cardinality stays.
    patterns = set(declared.patterns)
    patterns |= {
        p.pattern
        for p in observed.patterns
        if ({p.source, p.target} & new_nodes or p.relationship in new_rels)
        and p.pattern not in patterns
    }
    return replace(  # keeps everything else declared, e.g. constraints
        declared,
        node_types=node_types,
        relationship_types=relationship_types,
        patterns=tuple(sorted(patterns)),
        vocabularies=vocabularies,
    )


def apply_definitions(
    base: Ontology, candidate: Ontology, proposals: Mapping[str, str]
) -> tuple[Ontology, tuple[str, ...]]:
    """`candidate` with each proposed Definition applied to the Concept it names, if that
    Concept is one the candidate adds to `base` (a Class or Relation by `Label`, an
    Attribute by `Owner.name`); also the references of the proposals it ignored, sorted.

    Proposals never touch a Concept `base` declares: when a Class and a Relation share a
    label (or an Attribute name on such owners), a proposal applies only to the added one.
    """
    targets = {
        added: proposals[added.identity]
        for added in added_concepts(base, candidate)
        if added.identity in proposals
    }
    applied_refs = {added.identity for added in targets}
    ignored = tuple(sorted(ref for ref in proposals if ref not in applied_refs))
    if not targets:
        return candidate, ignored
    return (
        replace(
            candidate,
            node_types=tuple(
                _with_definitions(n, "node_type", targets) for n in candidate.node_types
            ),
            relationship_types=tuple(
                _with_definitions(r, "relationship_type", targets)
                for r in candidate.relationship_types
            ),
        ),
        ignored,
    )


def _with_definitions[C: (NodeType, RelationshipType)](
    concept: C, kind: ConceptKind, targets: Mapping[AddedConcept, str]
) -> C:
    """`concept` (of `kind`) with the Definitions `targets` holds for it and its own
    Attributes, each keyed by the added Concept it is (so never a declared Concept that
    merely shares a label)."""
    own_key = AddedConcept(kind, concept.label)

    def documented(p: Property) -> Property:
        text = targets.get(AddedConcept("property", f"{concept.label}.{p.name}", own_key.key))
        return p if text is None else replace(p, definition=text)

    properties = tuple(documented(p) for p in concept.properties)
    own = targets.get(own_key)
    return replace(
        concept,
        definition=concept.definition if own is None else own,
        properties=properties,
    )


def _extend_vocabularies(declared: Ontology, observed: ObservedSchema) -> tuple[Vocabulary, ...]:
    """The declared Vocabularies, each with the observed values outside it appended as new
    Values (sorted), whichever bound Attribute they were observed on. Only listed values are
    added: those beyond a truncated list's cap are unknown."""
    new: dict[str, set[str]] = {}
    owners = (
        (declared.node_types, observed.node_type, _properties_of(declared)),
        (declared.relationship_types, observed.relationship_type, _own_properties),
    )
    for concepts, observed_owner, properties_of in owners:
        for concept in concepts:
            o = observed_owner(concept.label)
            observed_props = {p.name: p for p in (o.properties if o else ())}
            for p in properties_of(concept):
                op = observed_props.get(p.name)
                if p.vocabulary and op is not None and op.values is not None:
                    new.setdefault(p.vocabulary, set()).update(c.value for c in op.values.counts)
    extended = []
    for vocabulary in declared.vocabularies:
        known = {v.label for v in vocabulary.values}
        added = sorted(new.get(vocabulary.label, set()) - known)
        extended.append(
            replace(vocabulary, values=vocabulary.values + tuple(VocabularyValue(v) for v in added))
            if added
            else vocabulary
        )
    return tuple(extended)


def _extend(declared, observed, concept_type, properties_of: PropertiesOf):
    """Declared Concepts with their undeclared observed properties added, plus the
    undeclared observed Concepts, sorted by label; also the new labels and whether any
    property was added to a declared Concept."""
    observed_by_label = {o.label: o for o in observed}
    declared_labels = {c.label for c in declared}
    extended = []
    added_properties = False
    for c in declared:
        o = observed_by_label.get(c.label)
        known = {p.name for p in properties_of(c)}  # inherited ones are not new
        extra = tuple(_property(p) for p in (o.properties if o else ()) if p.name not in known)
        added_properties = added_properties or bool(extra)
        extended.append(
            replace(c, properties=tuple(sorted(c.properties + extra, key=lambda p: p.name)))
            if extra
            else c
        )
    new_labels = set(observed_by_label) - declared_labels
    for label in new_labels:
        props = observed_by_label[label].properties
        extended.append(concept_type(label=label, properties=tuple(_property(p) for p in props)))
    return tuple(sorted(extended, key=lambda c: c.label)), new_labels, added_properties


def _property(observed: ObservedProperty) -> Property:
    """An optional property typed from the observation. Mixed INTEGER/FLOAT values widen
    to FLOAT; any other mix takes the first type name (alphabetically)."""
    types = set(observed.types)
    widened = {new for old, new in WIDENING_TYPE_CHANGES if {old, new} == types}
    return Property(name=observed.name, type=next(iter(widened), observed.types[0]))
