"""The formalism-independent internal Ontology model.

Every input format (today: the stetiq YAML) converts into these types; every
other module (diff, conformance, evaluators) works on them only.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

# The kinds of Concept: classes (node types), relations and attributes; and the Vocabularies
# attributes draw values from, whose Vocabulary Values the Diff identifies as `Vocabulary.value`.
ConceptKind = Literal["node_type", "relationship_type", "property", "vocabulary"]


@dataclass(frozen=True)
class Property:
    """An attribute Concept. Like every Concept it has a Definition and Alternative Labels.
    Its `replaced_by` names another attribute on the same owner. A STRING attribute may be
    bound to a Vocabulary by its label (`vocabulary`), and then takes only its values."""

    name: str
    type: str
    definition: str | None = None
    required: bool = False
    alternative_labels: tuple[str, ...] = ()
    deprecated: bool = False
    replaced_by: str | None = None
    deprecation_reason: str | None = None
    vocabulary: str | None = None


@dataclass(frozen=True)
class VocabularyValue:
    """One permitted value of a Vocabulary, identified by its label. Like a Concept it has a
    Definition, Alternative Labels and a Deprecation; its `replaced_by` names another value
    of the same Vocabulary."""

    label: str
    definition: str | None = None
    alternative_labels: tuple[str, ...] = ()
    deprecated: bool = False
    replaced_by: str | None = None
    deprecation_reason: str | None = None


@dataclass(frozen=True)
class Vocabulary:
    """A named, flat set of Vocabulary Values that any attribute bound to it may take."""

    label: str
    values: tuple[VocabularyValue, ...]
    definition: str | None = None
    alternative_labels: tuple[str, ...] = ()


@dataclass(frozen=True)
class NodeType:
    """A class Concept. `parent` is its superclass (single inheritance), if any."""

    label: str
    definition: str | None = None
    properties: tuple[Property, ...] = ()
    deprecated: bool = False
    replaced_by: str | None = None
    parent: str | None = None
    alternative_labels: tuple[str, ...] = ()
    deprecation_reason: str | None = None


@dataclass(frozen=True)
class RelationshipType:
    """A relation Concept."""

    label: str
    definition: str | None = None
    properties: tuple[Property, ...] = ()
    deprecated: bool = False
    replaced_by: str | None = None
    alternative_labels: tuple[str, ...] = ()
    deprecation_reason: str | None = None


@dataclass(frozen=True, order=True)
class Pattern:
    """An allowed endpoint pattern: (source node type)-[relationship type]->(target node type).

    A Pattern is identified by its three labels. Its optional cardinality bounds how many
    `relationship` edges each `source` node has to `target` nodes (`min_out`, `max_out`)
    and each `target` node has from `source` nodes (`min_in`, `max_in`); None leaves a
    bound open. The bounds are an Axiom on the Pattern, not part of its identity, so they
    do not take part in equality or ordering."""

    source: str
    relationship: str
    target: str
    min_out: int | None = field(default=None, compare=False)
    max_out: int | None = field(default=None, compare=False)
    min_in: int | None = field(default=None, compare=False)
    max_in: int | None = field(default=None, compare=False)

    @property
    def endpoints(self) -> Pattern:
        """This Pattern without its cardinality."""
        return Pattern(self.source, self.relationship, self.target)

    @property
    def cardinality(self) -> dict[str, dict[str, int]]:
        """The declared bounds in the stetiq YAML's shape, `{out: {min, max}, in: {min, max}}`,
        with open bounds and empty directions left out."""
        directions = {
            "out": {"min": self.min_out, "max": self.max_out},
            "in": {"min": self.min_in, "max": self.max_in},
        }
        return {
            direction: {k: v for k, v in bounds.items() if v is not None}
            for direction, bounds in directions.items()
            if any(v is not None for v in bounds.values())
        }

    def __str__(self) -> str:
        """`(Source)-[REL]->(Target)`, the syntax reports and Concept references use."""
        return f"({self.source})-[{self.relationship}]->({self.target})"


@dataclass(frozen=True, order=True)
class Constraint:
    """A property constraint on a node type, in neo4j-graphrag's shape.

    `property_name` may be declared on the node type or inherited from an ancestor.
    Only `UNIQUENESS` exists so far.
    """

    type: str
    node_type: str
    property_name: str


@dataclass(frozen=True)
class Ontology:
    node_types: tuple[NodeType, ...] = ()
    relationship_types: tuple[RelationshipType, ...] = ()
    patterns: tuple[Pattern, ...] = field(default=())
    constraints: tuple[Constraint, ...] = ()
    vocabularies: tuple[Vocabulary, ...] = ()

    def node_type(self, label: str) -> NodeType:
        return next(n for n in self.node_types if n.label == label)

    def relationship_type(self, label: str) -> RelationshipType:
        return next(r for r in self.relationship_types if r.label == label)

    def vocabulary(self, label: str) -> Vocabulary | None:
        return next((v for v in self.vocabularies if v.label == label), None)


def is_deprecated(c: NodeType | RelationshipType | Property | VocabularyValue) -> bool:
    """Deprecated, either flagged so or by naming a replacement."""
    return c.deprecated or c.replaced_by is not None


def live_concepts(
    ontology: Ontology,
) -> list[tuple[ConceptKind, str, NodeType | RelationshipType | Property]]:
    """Every Concept that is not deprecated, as (kind, identity, Concept), in declaration
    order: each class, then each relation, followed by its attributes (`Owner.name`). The
    attributes of a deprecated class or relation are left out with it."""
    out: list[tuple[ConceptKind, str, NodeType | RelationshipType | Property]] = []
    owners: list[tuple[ConceptKind, NodeType | RelationshipType]] = []
    owners.extend(("node_type", n) for n in ontology.node_types)
    owners.extend(("relationship_type", r) for r in ontology.relationship_types)
    for kind, owner in owners:
        if is_deprecated(owner):
            continue
        out.append((kind, owner.label, owner))
        out.extend(
            ("property", f"{owner.label}.{p.name}", p)
            for p in owner.properties
            if not is_deprecated(p)
        )
    return out
