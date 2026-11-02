"""Graph Source scope and the Observed Schema (structure + aggregate statistics, no instances)."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any, Literal, NamedTuple

from stetiq.ontology.model import Ontology, Pattern

# A namespace scope selects nodes whose property of this name equals the namespace.
NAMESPACE_PROPERTY = "namespace"


@dataclass(frozen=True)
class GraphSourceScope:
    """A database, optionally narrowed to nodes carrying `label` and/or whose
    `NAMESPACE_PROPERTY` equals `namespace`. A relationship is in scope when both its
    endpoints are. The scope label and the namespace property are scoping artefacts:
    they never appear in the Observed Schema."""

    database: str = "neo4j"
    label: str | None = None
    namespace: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"database": self.database, "label": self.label, "namespace": self.namespace}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> GraphSourceScope:
        return cls(database=d["database"], label=d.get("label"), namespace=d.get("namespace"))


#: How many distinct values Observation reads per Vocabulary-bound Attribute by default.
DEFAULT_VALUE_CAP = 100


class BoundAttribute(NamedTuple):
    """A Vocabulary-bound Attribute whose values Observation reads, as an
    `(owner kind, owner label, attribute)` triple."""

    owner_kind: Literal["node_type", "relationship_type"]
    owner: str
    attribute: str


def bound_attributes(ontology: Ontology) -> tuple[BoundAttribute, ...]:
    """Every Attribute of `ontology` bound to a Vocabulary: the only Attributes whose
    instance values Observation may read (ADR 0001)."""
    return tuple(
        BoundAttribute("node_type", n.label, p.name)
        for n in ontology.node_types
        for p in n.properties
        if p.vocabulary is not None
    ) + tuple(
        BoundAttribute("relationship_type", r.label, p.name)
        for r in ontology.relationship_types
        for p in r.properties
        if p.vocabulary is not None
    )


@dataclass(frozen=True)
class ValueCount:
    """One distinct string value of an Attribute and how many nodes or relationships of
    the owning type hold it."""

    value: str
    count: int


@dataclass(frozen=True)
class ObservedValues:
    """The distinct string values a Vocabulary-bound Attribute takes, most frequent first
    (ties by value), at most the cap of them. `truncated` says more distinct values exist
    than the cap let through, so the list is incomplete."""

    counts: tuple[ValueCount, ...]
    truncated: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "counts": [{"value": c.value, "count": c.count} for c in self.counts],
            "truncated": self.truncated,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> ObservedValues:
        return cls(
            tuple(ValueCount(c["value"], c["count"]) for c in d["counts"]), bool(d["truncated"])
        )

    @classmethod
    def capped(cls, counts: Iterable[tuple[str, int]], cap: int) -> ObservedValues:
        """The `cap` most frequent of `counts`, flagged `truncated` when there were more."""
        ordered = sorted(counts, key=lambda c: (-c[1], c[0]))
        return cls(tuple(ValueCount(v, n) for v, n in ordered[:cap]), len(ordered) > cap)


@dataclass(frozen=True)
class ObservedProperty:
    name: str
    types: tuple[str, ...]  # graphrag property type names (see ontology PROPERTY_TYPES), sorted
    count: int  # nodes or relationships of the owning type that have this property
    fill_rate: float  # count / owning type's count
    # Only for a Vocabulary-bound Attribute that Observation was asked to read; else None.
    values: ObservedValues | None = None
    # How many values of each type in `types` the property holds, as (type, count) sorted
    # by type. None when the Graph Source did not count them (an older or third-party
    # Observed Schema): the type-mismatch Violation Rate is then unknown.
    type_counts: tuple[tuple[str, int], ...] | None = None


@dataclass(frozen=True)
class ObservedNodeType:
    """A node label. A node with labels A:B counts once for A and once for B."""

    label: str
    count: int
    properties: tuple[ObservedProperty, ...] = ()  # sorted by name


@dataclass(frozen=True)
class ObservedRelationshipType:
    label: str
    count: int
    properties: tuple[ObservedProperty, ...] = ()  # sorted by name


@dataclass(frozen=True)
class Degree:
    """Distribution of per-node relationship counts (zero-degree nodes included)."""

    min: int
    max: int
    mean: float

    def to_dict(self) -> dict[str, Any]:
        return {"min": self.min, "max": self.max, "mean": self.mean}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Degree:
        return cls(d["min"], d["max"], float(d["mean"]))


@dataclass(frozen=True)
class ObservedPattern:
    """(source)-[relationship]->(target) with its count and cardinalities.

    `out_degree` is taken over every `source`-labelled node in scope: how many
    `relationship` edges it has to `target`-labelled nodes. `in_degree` mirrors it
    over every `target`-labelled node."""

    source: str
    relationship: str
    target: str
    count: int
    out_degree: Degree
    in_degree: Degree

    @property
    def pattern(self) -> Pattern:
        """The endpoint pattern observed, without its statistics."""
        return Pattern(self.source, self.relationship, self.target)


@dataclass(frozen=True)
class ObservedSchema:
    node_types: tuple[ObservedNodeType, ...] = ()  # sorted by label
    relationship_types: tuple[ObservedRelationshipType, ...] = ()  # sorted by label
    patterns: tuple[ObservedPattern, ...] = ()  # sorted by (source, relationship, target)

    def node_type(self, label: str) -> ObservedNodeType | None:
        return next((n for n in self.node_types if n.label == label), None)

    def relationship_type(self, label: str) -> ObservedRelationshipType | None:
        return next((r for r in self.relationship_types if r.label == label), None)

    def pattern(self, source: str, relationship: str, target: str) -> ObservedPattern | None:
        key = (source, relationship, target)
        return next((p for p in self.patterns if (p.source, p.relationship, p.target) == key), None)

    def to_dict(self) -> dict[str, Any]:
        def props(ps: tuple[ObservedProperty, ...]) -> list[dict[str, Any]]:
            return [
                {"name": p.name, "types": list(p.types), "count": p.count, "fill_rate": p.fill_rate}
                | ({} if p.values is None else {"values": p.values.to_dict()})
                | ({} if p.type_counts is None else {"type_counts": dict(p.type_counts)})
                for p in ps
            ]

        return {
            "node_types": [
                {"label": n.label, "count": n.count, "properties": props(n.properties)}
                for n in self.node_types
            ],
            "relationship_types": [
                {"label": r.label, "count": r.count, "properties": props(r.properties)}
                for r in self.relationship_types
            ],
            "patterns": [
                {
                    "source": p.source,
                    "relationship": p.relationship,
                    "target": p.target,
                    "count": p.count,
                    "out_degree": p.out_degree.to_dict(),
                    "in_degree": p.in_degree.to_dict(),
                }
                for p in self.patterns
            ],
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> ObservedSchema:
        def props(ps: list[dict[str, Any]]) -> tuple[ObservedProperty, ...]:
            return tuple(
                ObservedProperty(
                    p["name"],
                    tuple(p["types"]),
                    p["count"],
                    float(p["fill_rate"]),
                    None if p.get("values") is None else ObservedValues.from_dict(p["values"]),
                    None
                    if p.get("type_counts") is None
                    else tuple(sorted((t, int(n)) for t, n in p["type_counts"].items())),
                )
                for p in ps
            )

        return cls(
            node_types=tuple(
                ObservedNodeType(n["label"], n["count"], props(n["properties"]))
                for n in d["node_types"]
            ),
            relationship_types=tuple(
                ObservedRelationshipType(r["label"], r["count"], props(r["properties"]))
                for r in d["relationship_types"]
            ),
            patterns=tuple(
                ObservedPattern(
                    p["source"],
                    p["relationship"],
                    p["target"],
                    p["count"],
                    Degree.from_dict(p["out_degree"]),
                    Degree.from_dict(p["in_degree"]),
                )
                for p in d["patterns"]
            ),
        )
