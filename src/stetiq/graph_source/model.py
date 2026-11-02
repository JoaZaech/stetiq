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


class PatternBound(NamedTuple):
    """A Pattern's declared cardinality in one direction, as handed to the adapter:
    `out` bounds how many `relationship` edges each `source` node has to `target` nodes,
    `in` how many each `target` node has from `source` nodes. None leaves a side open."""

    source: str
    relationship: str
    target: str
    direction: Literal["out", "in"]
    min: int | None
    max: int | None


def pattern_bounds(ontology: Ontology) -> tuple[PatternBound, ...]:
    """Every declared cardinality bound of `ontology`'s Patterns, one per bounded
    direction: what Observation counts the endpoint nodes outside of."""
    bounds = [
        bound
        for p in ontology.patterns
        for bound in (
            PatternBound(p.source, p.relationship, p.target, "out", p.min_out, p.max_out),
            PatternBound(p.source, p.relationship, p.target, "in", p.min_in, p.max_in),
        )
    ]
    return tuple(b for b in bounds if b.min is not None or b.max is not None)


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
class OutsideBounds:
    """How many endpoint nodes have a degree outside the declared `[min, max]` (None
    leaves a side open); a zero-degree node counts against a `min`. The bounds are kept
    so that a count is only compared with the same bounds."""

    min: int | None
    max: int | None
    count: int

    def to_dict(self) -> dict[str, Any]:
        return {"min": self.min, "max": self.max, "count": self.count}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> OutsideBounds:
        return cls(d.get("min"), d.get("max"), d["count"])


@dataclass(frozen=True)
class Degree:
    """Distribution of per-node relationship counts (zero-degree nodes included).

    `with_edges` is how many endpoint nodes have at least one such relationship; it
    divided by the endpoint count is the pattern's Coverage. None when the adapter (or a
    stored or pushed Observed Schema) predates it.

    `outside_bounds` is set only when Observation was given a declared bound for this
    Pattern and direction; schemas observed without one (or before it existed) lack it."""

    min: int
    max: int
    mean: float
    with_edges: int | None = None
    outside_bounds: OutsideBounds | None = None

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"min": self.min, "max": self.max, "mean": self.mean}
        if self.with_edges is not None:
            d["with_edges"] = self.with_edges
        if self.outside_bounds is not None:
            d["outside_bounds"] = self.outside_bounds.to_dict()
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Degree:
        outside = d.get("outside_bounds")
        return cls(
            d["min"],
            d["max"],
            float(d["mean"]),
            with_edges=d.get("with_edges"),
            outside_bounds=None if outside is None else OutsideBounds.from_dict(outside),
        )


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
