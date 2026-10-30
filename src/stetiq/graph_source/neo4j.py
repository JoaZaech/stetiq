"""The Neo4j Graph Source adapter: read-only Observation over plain, scopeable Cypher.

Every query runs in a read transaction (`session.execute_read`, access mode READ), and
`execute_read` additionally rejects any query whose EXPLAIN plan is not read-only. The
driver docs warn that read mode is not access control: for real enforcement connect as a
least-privilege user (Enterprise/Aura: the built-in `reader` role).

Observation computes only aggregates server-side (counts, fill rates, degree min/max/sum)
so no individual entity crosses into stetiq (ADR 0001). No APOC is required; `valueType()`
needs Neo4j 5.13+.
"""

from __future__ import annotations

import os
import re
from collections.abc import Mapping
from typing import Any
from urllib.parse import unquote, urlsplit, urlunsplit

import neo4j

from stetiq.errors import GraphSourceWriteRejectedError
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

URI_ENV = "STETIQ_GRAPH_SOURCE_URI"
USER_ENV = "STETIQ_GRAPH_SOURCE_USER"
PASSWORD_ENV = "STETIQ_GRAPH_SOURCE_PASSWORD"


class Neo4jGraphSource:
    """Graph Source adapter over a Neo4j driver. Build it with `connect(uri, ...)` (it then
    owns and closes the driver) or hand it an existing `neo4j.Driver`."""

    def __init__(self, driver: neo4j.Driver, *, owns_driver: bool = False) -> None:
        self._driver = driver
        self._owns_driver = owns_driver

    @classmethod
    def connect(
        cls, uri: str, *, user: str | None = None, password: str | None = None
    ) -> Neo4jGraphSource:
        """Connect to `uri` (`bolt://`, `neo4j://`, `neo4j+s://`, ...). Credentials may be
        given as arguments or as userinfo in the URI (`neo4j://user:pw@host:7687`)."""
        parts = urlsplit(uri)
        if parts.username is not None:
            user = user or unquote(parts.username)
            password = password or unquote(parts.password or "")
            netloc = parts.hostname or ""
            if parts.port is not None:
                netloc += f":{parts.port}"
            uri = urlunsplit(parts._replace(netloc=netloc))
        auth = (user, password or "") if user is not None else None
        return cls(neo4j.GraphDatabase.driver(uri, auth=auth), owns_driver=True)

    def close(self) -> None:
        if self._owns_driver:
            self._driver.close()

    def __enter__(self) -> Neo4jGraphSource:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # --- GraphSource ----------------------------------------------------------------

    def execute_read(
        self, scope: GraphSourceScope, query: str, parameters: Mapping[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        params = dict(parameters or {})

        def work(tx: neo4j.ManagedTransaction) -> list[dict[str, Any]]:
            plan = tx.run(f"EXPLAIN {query}", params).consume()
            if plan.query_type != "r":
                raise GraphSourceWriteRejectedError(
                    f"Graph Source queries must be read-only; query type is {plan.query_type!r}"
                )
            return [record.data() for record in tx.run(query, params)]

        with self._session(scope) as session:
            return session.execute_read(work)

    def observe(self, scope: GraphSourceScope) -> ObservedSchema:
        params = {"scope_label": scope.label, "namespace": scope.namespace}
        with self._session(scope) as session:
            rows = session.execute_read(
                lambda tx: {name: tx.run(q, params).data() for name, q in _queries(scope).items()}
            )

        node_counts = {r["label"]: r["count"] for r in rows["node_counts"]}
        rel_counts = {r["type"]: r["count"] for r in rows["rel_counts"]}
        node_props = _group_properties(rows["node_properties"], node_counts)
        rel_props = _group_properties(rows["rel_properties"], rel_counts)
        out_stats = {(r["source"], r["type"], r["target"]): r for r in rows["out_degrees"]}
        in_stats = {(r["source"], r["type"], r["target"]): r for r in rows["in_degrees"]}

        return ObservedSchema(
            node_types=tuple(
                ObservedNodeType(label, count, node_props.get(label, ()))
                for label, count in sorted(node_counts.items())
            ),
            relationship_types=tuple(
                ObservedRelationshipType(type_, count, rel_props.get(type_, ()))
                for type_, count in sorted(rel_counts.items())
            ),
            patterns=tuple(
                ObservedPattern(
                    source=source,
                    relationship=type_,
                    target=target,
                    count=out_stats[(source, type_, target)]["total"],
                    out_degree=_degree(out_stats[(source, type_, target)], node_counts[source]),
                    in_degree=_degree(in_stats[(source, type_, target)], node_counts[target]),
                )
                for source, type_, target in sorted(out_stats)
            ),
        )

    def _session(self, scope: GraphSourceScope) -> neo4j.Session:
        return self._driver.session(
            database=scope.database, default_access_mode=neo4j.READ_ACCESS
        )


def graph_source_from_env(environ: Mapping[str, str] | None = None) -> Neo4jGraphSource | None:
    """The adapter configured by `STETIQ_GRAPH_SOURCE_URI` (+ `_USER` / `_PASSWORD`), or
    None when no URI is set. Credentials stay in the user's process; they are never sent
    to the tracking service."""
    env = os.environ if environ is None else environ
    uri = env.get(URI_ENV)
    if not uri:
        return None
    return Neo4jGraphSource.connect(uri, user=env.get(USER_ENV), password=env.get(PASSWORD_ENV))


# --- Cypher ----------------------------------------------------------------------------


def _quote(name: str) -> str:
    """Backtick-quote a label or type (Cypher cannot parameterise them)."""
    return "`" + name.replace("`", "``") + "`"


def _in_scope(var: str, scope: GraphSourceScope) -> str:
    conditions = []
    if scope.label is not None:
        conditions.append(f"{var}:{_quote(scope.label)}")
    if scope.namespace is not None:
        conditions.append(f"{var}.{_quote(NAMESPACE_PROPERTY)} = $namespace")
    return " AND ".join(conditions) or "true"


# Labels of a node, minus the scope label (a scoping artefact).
def _labels(var: str) -> str:
    return f"[l IN labels({var}) WHERE $scope_label IS NULL OR l <> $scope_label]"


def _queries(scope: GraphSourceScope) -> dict[str, str]:
    a, b, n = _in_scope("a", scope), _in_scope("b", scope), _in_scope("n", scope)
    # Node keys minus the namespace property when scoping by namespace.
    node_keys = f"[k IN keys(n) WHERE $namespace IS NULL OR k <> '{NAMESPACE_PROPERTY}']"
    pattern = f"""
        MATCH (a)-[r]->(b) WHERE {a} AND {b}
        UNWIND {_labels("a")} AS source
        UNWIND {_labels("b")} AS target
    """
    return {
        "node_counts": f"""
            MATCH (n) WHERE {n}
            UNWIND {_labels("n")} AS label
            RETURN label, count(*) AS count
        """,
        "node_properties": f"""
            MATCH (n) WHERE {n}
            UNWIND {_labels("n")} AS owner
            UNWIND {node_keys} AS key
            RETURN owner, key, count(*) AS filled, collect(DISTINCT valueType(n[key])) AS types
        """,
        "rel_counts": f"""
            MATCH (a)-[r]->(b) WHERE {a} AND {b}
            RETURN type(r) AS type, count(*) AS count
        """,
        "rel_properties": f"""
            MATCH (a)-[r]->(b) WHERE {a} AND {b}
            UNWIND keys(r) AS key
            RETURN type(r) AS owner, key, count(*) AS filled,
                   collect(DISTINCT valueType(r[key])) AS types
        """,
        # Degree stats over nodes with at least one edge; zero-degree nodes are added
        # back in Python from the label counts.
        "out_degrees": f"""
            {pattern}
            WITH source, type(r) AS type, target, a, count(*) AS d
            RETURN source, type, target, sum(d) AS total, min(d) AS min, max(d) AS max,
                   count(a) AS nodes
        """,
        "in_degrees": f"""
            {pattern}
            WITH source, type(r) AS type, target, b, count(*) AS d
            RETURN source, type, target, sum(d) AS total, min(d) AS min, max(d) AS max,
                   count(b) AS nodes
        """,
    }


def _group_properties(
    rows: list[dict[str, Any]], owner_counts: Mapping[str, int]
) -> dict[str, tuple[ObservedProperty, ...]]:
    grouped: dict[str, list[ObservedProperty]] = {}
    for row in rows:
        owner, filled = row["owner"], row["filled"]
        types = tuple(sorted({_type_name(t) for t in row["types"]}))
        grouped.setdefault(owner, []).append(
            ObservedProperty(row["key"], types, filled, filled / owner_counts[owner])
        )
    return {owner: tuple(sorted(ps, key=lambda p: p.name)) for owner, ps in grouped.items()}


def _degree(stats: Mapping[str, Any], endpoint_count: int) -> Degree:
    """Degree over all `endpoint_count` nodes, `stats` covering only those with edges."""
    has_zero_degree_nodes = stats["nodes"] < endpoint_count
    return Degree(
        min=0 if has_zero_degree_nodes else stats["min"],
        max=stats["max"],
        mean=stats["total"] / endpoint_count,
    )


_NOT_NULL = re.compile(r"\s+NOT NULL$")


def _type_name(value_type: str) -> str:
    """Neo4j `valueType()` (e.g. 'LOCAL DATETIME NOT NULL', 'LIST<STRING NOT NULL> NOT NULL')
    -> graphrag property type name ('LOCAL_DATETIME', 'LIST')."""
    name = _NOT_NULL.sub("", value_type.strip())
    if name.startswith("LIST"):
        return "LIST"
    return name.replace(" ", "_")
