"""Writing the plant graph into a Neo4j database.

The pipeline writes every Construction Run's Extraction into the candidate graph, and
`deploy` writes a promoted run's Extraction into the production graph, both through
`write`. stetiq itself never writes: it reads the candidate graph read-only through its
Neo4j Graph Source.
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass
from typing import Any, LiteralString, cast

import neo4j

Key = tuple[str, str]  # (label, key): how the pipeline names a node
_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


@dataclass(frozen=True)
class Extraction:
    """What one Construction Run built: its nodes (label, key, typed properties) and the
    relationships between them, by node key."""

    nodes: tuple[tuple[str, str, dict[str, Any]], ...]
    relationships: tuple[tuple[Key, str, Key], ...]


def _name(name: str) -> str:
    """A label or relationship type, checked before it goes into Cypher (neither can be
    a query parameter)."""
    if not _NAME.match(name):
        raise ValueError(f"not a label or relationship type the graph accepts: {name!r}")
    return f"`{name}`"


def write(driver: neo4j.Driver, extraction: Extraction, *, database: str) -> tuple[int, int]:
    """Replace everything in `database` with `extraction`; returns the number of nodes and
    relationships written."""
    by_label: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for label, key, properties in extraction.nodes:
        by_label[label].append({"key": key, "properties": properties})
    by_type: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for (start_label, start_key), type_, (end_label, end_key) in extraction.relationships:
        by_type[type_].append(
            {"start": f"{start_label}\x00{start_key}", "end": f"{end_label}\x00{end_key}"}
        )

    def work(tx: neo4j.ManagedTransaction) -> None:
        tx.run("MATCH (n) DETACH DELETE n").consume()
        ids: dict[str, str] = {}
        for label, rows in by_label.items():
            records = tx.run(
                _cypher(
                    f"UNWIND $rows AS row CREATE (n:{_name(label)}) SET n = row.properties "
                    "RETURN row.key AS key, elementId(n) AS id"
                ),
                rows=rows,
            )
            ids.update({f"{label}\x00{r['key']}": r["id"] for r in records})
        for type_, rows in by_type.items():
            pairs = [{"start": ids[r["start"]], "end": ids[r["end"]]} for r in rows]
            tx.run(
                _cypher(
                    "UNWIND $pairs AS pair MATCH (a) WHERE elementId(a) = pair.start "
                    "MATCH (b) WHERE elementId(b) = pair.end "
                    f"CREATE (a)-[:{_name(type_)}]->(b)"
                ),
                pairs=pairs,
            ).consume()

    with driver.session(database=database) as session:
        session.execute_write(work)
    return len(extraction.nodes), len(extraction.relationships)


def _cypher(query: str) -> LiteralString:
    # Labels and types are checked by `_name`; values travel as parameters.
    return cast(LiteralString, query)
