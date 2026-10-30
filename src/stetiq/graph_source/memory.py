"""In-memory fake Graph Source for tests.

Seeded with nodes and relationships (the test plays the role of the user's extraction workflow
writing into the graph database), it computes the Observed Schema the same way the
Neo4j adapter's scoped Cypher does, so the shared contract suite keeps it honest.
`execute_read` returns canned results registered with `add_query_result`.
"""

from __future__ import annotations

import datetime as dt
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

from stetiq.graph_source.model import (
    NAMESPACE_PROPERTY,
    Degree,
    GraphSourceScope,
    ObservedNodeType,
    ObservedPattern,
    ObservedProperty,
    ObservedRelationshipType,
    ObservedSchema,
)


@dataclass
class _Node:
    id: int
    database: str
    labels: frozenset[str]
    properties: dict[str, Any] = field(default_factory=dict)


@dataclass
class _Relationship:
    start: int
    type: str
    end: int
    properties: dict[str, Any] = field(default_factory=dict)


class InMemoryGraphSource:
    def __init__(self) -> None:
        self._nodes: dict[int, _Node] = {}
        self._relationships: list[_Relationship] = []
        self._query_results: dict[tuple[str, str], list[dict[str, Any]]] = {}

    # --- seeding (test-side writes; adapters themselves never write) --------------------

    def add_node(
        self,
        labels: Iterable[str],
        properties: Mapping[str, Any] | None = None,
        *,
        database: str = "neo4j",
    ) -> int:
        node_id = len(self._nodes)
        self._nodes[node_id] = _Node(node_id, database, frozenset(labels), dict(properties or {}))
        return node_id

    def add_relationship(
        self, start: int, type_: str, end: int, properties: Mapping[str, Any] | None = None
    ) -> None:
        if self._nodes[start].database != self._nodes[end].database:
            raise ValueError("a relationship cannot span databases")
        self._relationships.append(_Relationship(start, type_, end, dict(properties or {})))

    def add_query_result(
        self, query: str, rows: list[dict[str, Any]], *, database: str = "neo4j"
    ) -> None:
        self._query_results[(database, query)] = rows

    # --- GraphSource ----------------------------------------------------------------

    def execute_read(
        self, scope: GraphSourceScope, query: str, parameters: Mapping[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        try:
            return [dict(r) for r in self._query_results[(scope.database, query)]]
        except KeyError:
            raise ValueError(f"no canned result for query {query!r}") from None

    def observe(self, scope: GraphSourceScope) -> ObservedSchema:
        nodes = {n.id: n for n in self._nodes.values() if _in_scope(n, scope)}
        rels = [r for r in self._relationships if r.start in nodes and r.end in nodes]

        def labels(node: _Node) -> list[str]:
            return sorted(node.labels - {scope.label})

        def props(node: _Node) -> dict[str, Any]:
            if scope.namespace is None:
                return node.properties
            return {k: v for k, v in node.properties.items() if k != NAMESPACE_PROPERTY}

        nodes_by_label: dict[str, list[_Node]] = defaultdict(list)
        for node in nodes.values():
            for label in labels(node):
                nodes_by_label[label].append(node)
        rels_by_type: dict[str, list[_Relationship]] = defaultdict(list)
        for rel in rels:
            rels_by_type[rel.type].append(rel)

        node_types = tuple(
            ObservedNodeType(label, len(ns), _observed_properties([props(n) for n in ns]))
            for label, ns in sorted(nodes_by_label.items())
        )
        relationship_types = tuple(
            ObservedRelationshipType(t, len(rs), _observed_properties([r.properties for r in rs]))
            for t, rs in sorted(rels_by_type.items())
        )

        # (source label, type, target label) -> per-endpoint relationship counts
        out_counts: dict[tuple[str, str, str], Counter[int]] = defaultdict(Counter)
        in_counts: dict[tuple[str, str, str], Counter[int]] = defaultdict(Counter)
        for rel in rels:
            for la in labels(nodes[rel.start]):
                for lb in labels(nodes[rel.end]):
                    out_counts[(la, rel.type, lb)][rel.start] += 1
                    in_counts[(la, rel.type, lb)][rel.end] += 1
        patterns = tuple(
            ObservedPattern(
                source=source,
                relationship=type_,
                target=target,
                count=sum(out_counts[(source, type_, target)].values()),
                out_degree=_degree(out_counts[(source, type_, target)], nodes_by_label[source]),
                in_degree=_degree(in_counts[(source, type_, target)], nodes_by_label[target]),
            )
            for source, type_, target in sorted(out_counts)
        )
        return ObservedSchema(node_types, relationship_types, patterns)


def _in_scope(node: _Node, scope: GraphSourceScope) -> bool:
    if node.database != scope.database:
        return False
    if scope.label is not None and scope.label not in node.labels:
        return False
    return scope.namespace is None or node.properties.get(NAMESPACE_PROPERTY) == scope.namespace


def _observed_properties(records: list[dict[str, Any]]) -> tuple[ObservedProperty, ...]:
    total = len(records)
    types: dict[str, set[str]] = defaultdict(set)
    filled: Counter[str] = Counter()
    for record in records:
        for name, value in record.items():
            if value is None:
                continue
            filled[name] += 1
            types[name].add(_type_name(value))
    return tuple(
        ObservedProperty(name, tuple(sorted(types[name])), filled[name], filled[name] / total)
        for name in sorted(filled)
    )


def _degree(counts: Counter[int], endpoint_nodes: list[_Node]) -> Degree:
    degrees = [counts.get(n.id, 0) for n in endpoint_nodes]
    return Degree(min=min(degrees), max=max(degrees), mean=sum(degrees) / len(degrees))


def _type_name(value: Any) -> str:
    """Python value -> graphrag property type name (what Neo4j's valueType() maps to)."""
    if isinstance(value, bool):
        return "BOOLEAN"
    if isinstance(value, int):
        return "INTEGER"
    if isinstance(value, float):
        return "FLOAT"
    if isinstance(value, str):
        return "STRING"
    if isinstance(value, list | tuple):
        return "LIST"
    if isinstance(value, dt.datetime):
        return "LOCAL_DATETIME" if value.tzinfo is None else "ZONED_DATETIME"
    if isinstance(value, dt.date):
        return "DATE"
    if isinstance(value, dt.time):
        return "LOCAL_TIME" if value.tzinfo is None else "ZONED_TIME"
    if isinstance(value, dt.timedelta):
        return "DURATION"
    raise TypeError(f"unsupported property value {value!r}")
