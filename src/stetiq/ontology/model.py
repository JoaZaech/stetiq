"""The formalism-independent internal Ontology model.

Every input format (today: the stetiq YAML) converts into these types; every
other module (diff, conformance, evaluators) works on them only.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

# The kinds of Concept: classes (node types), relations and attributes.
ConceptKind = Literal["node_type", "relationship_type", "property"]


@dataclass(frozen=True)
class Property:
    name: str
    type: str
    description: str | None = None
    required: bool = False


@dataclass(frozen=True)
class NodeType:
    """A class Concept. `parent` is its superclass (single inheritance), if any."""

    label: str
    description: str | None = None
    properties: tuple[Property, ...] = ()
    deprecated: bool = False
    replaced_by: str | None = None
    parent: str | None = None


@dataclass(frozen=True)
class RelationshipType:
    """A relation Concept."""

    label: str
    description: str | None = None
    properties: tuple[Property, ...] = ()
    deprecated: bool = False
    replaced_by: str | None = None


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

    def node_type(self, label: str) -> NodeType:
        return next(n for n in self.node_types if n.label == label)

    def relationship_type(self, label: str) -> RelationshipType:
        return next(r for r in self.relationship_types if r.label == label)
