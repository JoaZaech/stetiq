"""A file-backed stand-in for the plant's graph database.

In production the pipeline writes to Neo4j and stetiq observes it through
`stetiq.graph_source.Neo4jGraphSource`. This example has to run on a laptop with
no services, so `LocalGraph` keeps the nodes and relationships in one JSON file
and implements stetiq's `GraphSource` protocol:

- `observe(scope)` hands the stored graph to stetiq's own `InMemoryGraphSource`,
  so the Observed Schema (labels, counts, fill rates, cardinalities) is computed
  the same way the real adapters compute it;
- `execute_read(scope, query)` answers the fixed set of Cypher queries the
  example uses (the Competency Questions in use-case.yaml and the queries of
  the custom Evaluators). They are matched by text in `QUERIES`; anything else
  raises `UnsupportedQueryError`, which stetiq records as a failed question.

The pipeline and the demo's "someone edited the database by hand" step use the
write methods. stetiq itself never writes.
"""

from __future__ import annotations

import datetime as dt
import json
import re
from collections import defaultdict
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from stetiq.graph_source import GraphSourceScope, InMemoryGraphSource, ObservedSchema

DEFAULT_DATABASE = "plant"


@dataclass
class Node:
    id: int
    database: str
    labels: list[str]
    properties: dict[str, Any] = field(default_factory=dict)


@dataclass
class Relationship:
    start: int
    type: str
    end: int
    properties: dict[str, Any] = field(default_factory=dict)


class UnsupportedQueryError(Exception):
    """The local store has no implementation for this query text."""


class LocalGraph:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self._nodes: dict[int, Node] = {}
        self._relationships: list[Relationship] = []
        self.load()

    # --- persistence ----------------------------------------------------------------

    def load(self) -> None:
        self._nodes.clear()
        self._relationships.clear()
        if not self.path.exists():
            return
        data = json.loads(self.path.read_text(encoding="utf-8"))
        for n in data["nodes"]:
            self._nodes[n["id"]] = Node(
                n["id"], n["database"], list(n["labels"]), _decode(n["properties"])
            )
        for r in data["relationships"]:
            self._relationships.append(
                Relationship(r["start"], r["type"], r["end"], _decode(r.get("properties", {})))
            )

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "nodes": [
                {
                    "id": n.id,
                    "database": n.database,
                    "labels": n.labels,
                    "properties": _encode(n.properties),
                }
                for n in self._nodes.values()
            ],
            "relationships": [
                {
                    "start": r.start,
                    "type": r.type,
                    "end": r.end,
                    "properties": _encode(r.properties),
                }
                for r in self._relationships
            ],
        }
        self.path.write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")

    # --- writes (the pipeline's side; stetiq never calls these) ---------------------

    def clear(self, database: str = DEFAULT_DATABASE) -> None:
        """Drop everything in `database`, the way the pipeline truncates its scope before a rebuild."""
        gone = {n.id for n in self._nodes.values() if n.database == database}
        self._nodes = {i: n for i, n in self._nodes.items() if i not in gone}
        self._relationships = [
            r for r in self._relationships if r.start not in gone and r.end not in gone
        ]

    def add_node(
        self,
        labels: Iterable[str],
        properties: Mapping[str, Any] | None = None,
        *,
        database: str = DEFAULT_DATABASE,
    ) -> int:
        node_id = max(self._nodes, default=-1) + 1
        self._nodes[node_id] = Node(node_id, database, list(labels), dict(properties or {}))
        return node_id

    def add_relationship(
        self, start: int, type_: str, end: int, properties: Mapping[str, Any] | None = None
    ) -> None:
        self._relationships.append(Relationship(start, type_, end, dict(properties or {})))

    def delete_nodes(
        self,
        label: str,
        *,
        database: str = DEFAULT_DATABASE,
        where: Callable[[dict[str, Any]], bool] | None = None,
    ) -> int:
        """Delete the nodes with `label` (that satisfy `where`) and their relationships."""
        gone = {
            n.id
            for n in self._nodes.values()
            if n.database == database
            and label in n.labels
            and (where is None or where(n.properties))
        }
        self._nodes = {i: n for i, n in self._nodes.items() if i not in gone}
        self._relationships = [
            r for r in self._relationships if r.start not in gone and r.end not in gone
        ]
        return len(gone)

    # --- reads used by the query implementations ------------------------------------

    def nodes(self, label: str, database: str = DEFAULT_DATABASE) -> list[Node]:
        return [n for n in self._nodes.values() if n.database == database and label in n.labels]

    def find(self, label: str, database: str = DEFAULT_DATABASE, **properties: Any) -> Node | None:
        for n in self.nodes(label, database):
            if all(n.properties.get(k) == v for k, v in properties.items()):
                return n
        return None

    def out(self, node_id: int, type_: str) -> list[Node]:
        return [
            self._nodes[r.end]
            for r in self._relationships
            if r.start == node_id and r.type == type_
        ]

    def in_(self, node_id: int, type_: str) -> list[Node]:
        return [
            self._nodes[r.start]
            for r in self._relationships
            if r.end == node_id and r.type == type_
        ]

    def count(self, label: str, database: str = DEFAULT_DATABASE) -> int:
        return len(self.nodes(label, database))

    # --- stetiq's GraphSource protocol ----------------------------------------------

    def observe(self, scope: GraphSourceScope) -> ObservedSchema:
        """Reload the file (another process may have written it) and let stetiq's
        in-memory adapter compute the Observed Schema."""
        self.load()
        memory = InMemoryGraphSource()
        ids: dict[int, int] = {}
        for node in self._nodes.values():
            ids[node.id] = memory.add_node(node.labels, node.properties, database=node.database)
        for rel in self._relationships:
            memory.add_relationship(ids[rel.start], rel.type, ids[rel.end], rel.properties)
        return memory.observe(scope)

    def execute_read(
        self, scope: GraphSourceScope, query: str, parameters: Mapping[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        self.load()
        try:
            implementation = QUERIES[_normalise(query)]
        except KeyError:
            raise UnsupportedQueryError(f"no implementation for query {query!r}") from None
        return implementation(self, scope.database)


# --- JSON encoding of property values -------------------------------------------------


def _encode(properties: Mapping[str, Any]) -> dict[str, Any]:
    return {
        k: {"$date": v.isoformat()} if isinstance(v, dt.date) else v for k, v in properties.items()
    }


def _decode(properties: Mapping[str, Any]) -> dict[str, Any]:
    return {
        k: dt.date.fromisoformat(v["$date"]) if isinstance(v, dict) and "$date" in v else v
        for k, v in properties.items()
    }


# --- The queries the local store can answer ------------------------------------------
#
# Each entry maps the Cypher text (whitespace-normalised) to a function computing the
# same rows over the stored graph. On Neo4j these strings would simply be executed.

Rows = list[dict[str, Any]]
QueryImpl = Callable[[LocalGraph, str], Rows]
QUERIES: dict[str, QueryImpl] = {}


def _normalise(query: str) -> str:
    return re.sub(r"\s+", " ", query).strip()


def query(text: str) -> Callable[[QueryImpl], QueryImpl]:
    def register(fn: QueryImpl) -> QueryImpl:
        QUERIES[_normalise(text)] = fn
        return fn

    return register


ORDERS_PER_MACHINE = """
MATCH (w:WorkOrder)-[:PERFORMED_ON]->(m:Machine)
RETURN m.name AS machine, count(w) AS work_orders ORDER BY work_orders DESC
"""
BREAKDOWN_TECHNICIANS = """
MATCH (w:WorkOrder {kind: 'breakdown'})-[:ASSIGNED_TO]->(t:Technician)
RETURN w.id AS work_order, t.name AS technician
"""
OPEN_FOLLOW_UPS = """
MATCH (w:WorkOrder)-[:HAS_FOLLOW_UP]->(f:FollowUp {status: 'open'})-[:ASSIGNED_TO]->(t:Technician)
RETURN w.id AS work_order, f.description AS follow_up, t.name AS owner
"""
DOWNSTREAM_OF_PRESS = """
MATCH (:Machine {name: 'Press-02'})-[:FEEDS*1..3]->(m:Machine)
RETURN DISTINCT m.name AS machine
"""
ROOT_CAUSES = """
MATCH (w:WorkOrder)-[:CAUSED_BY]->(f:Fault)
RETURN w.id AS work_order, f.description AS fault
"""
DOWNTIME_BY_KIND = """
MATCH (w:WorkOrder)
RETURN w.kind AS kind, sum(w.downtime_minutes) AS downtime_minutes
"""
PARTS_SUPPLIERS = """
MATCH (c:Component)-[:SUPPLIED_BY]->(s:Supplier)
RETURN c.name AS component, s.name AS supplier
"""
WORK_ORDER_COUNT = "MATCH (w:WorkOrder) RETURN count(w) AS work_orders"
WORK_ORDERS_WITHOUT_FOLLOW_UPS = """
MATCH (w:WorkOrder) WHERE NOT (w)-[:HAS_FOLLOW_UP]->(:FollowUp)
RETURN count(w) AS work_orders
"""


@query(ORDERS_PER_MACHINE)
def _orders_per_machine(g: LocalGraph, db: str) -> Rows:
    counts: dict[str, int] = defaultdict(int)
    for w in g.nodes("WorkOrder", db):
        for m in g.out(w.id, "PERFORMED_ON"):
            counts[m.properties["name"]] += 1
    return [
        {"machine": name, "work_orders": n}
        for name, n in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    ]


@query(BREAKDOWN_TECHNICIANS)
def _breakdown_technicians(g: LocalGraph, db: str) -> Rows:
    return [
        {"work_order": w.properties["id"], "technician": t.properties["name"]}
        for w in g.nodes("WorkOrder", db)
        if w.properties.get("kind") == "breakdown"
        for t in g.out(w.id, "ASSIGNED_TO")
        if "Technician" in t.labels
    ]


@query(OPEN_FOLLOW_UPS)
def _open_follow_ups(g: LocalGraph, db: str) -> Rows:
    return [
        {
            "work_order": w.properties["id"],
            "follow_up": f.properties["description"],
            "owner": t.properties["name"],
        }
        for w in g.nodes("WorkOrder", db)
        for f in g.out(w.id, "HAS_FOLLOW_UP")
        if f.properties.get("status") == "open"
        for t in g.out(f.id, "ASSIGNED_TO")
    ]


@query(DOWNSTREAM_OF_PRESS)
def _downstream_of_press(g: LocalGraph, db: str) -> Rows:
    start = g.find("Machine", db, name="Press-02")
    if start is None:
        return []
    reached: dict[str, None] = {}
    frontier = [start]
    for _ in range(3):
        frontier = [
            m for node in frontier for m in g.out(node.id, "FEEDS") if "Machine" in m.labels
        ]
        for m in frontier:
            reached.setdefault(m.properties["name"], None)
    return [{"machine": name} for name in reached]


@query(ROOT_CAUSES)
def _root_causes(g: LocalGraph, db: str) -> Rows:
    return [
        {"work_order": w.properties["id"], "fault": f.properties["description"]}
        for w in g.nodes("WorkOrder", db)
        for f in g.out(w.id, "CAUSED_BY")
    ]


@query(DOWNTIME_BY_KIND)
def _downtime_by_kind(g: LocalGraph, db: str) -> Rows:
    totals: dict[str, int] = defaultdict(int)
    for w in g.nodes("WorkOrder", db):
        totals[w.properties.get("kind")] += int(w.properties.get("downtime_minutes") or 0)
    return [{"kind": kind, "downtime_minutes": total} for kind, total in sorted(totals.items())]


@query(PARTS_SUPPLIERS)
def _parts_suppliers(g: LocalGraph, db: str) -> Rows:
    return [
        {"component": c.properties["name"], "supplier": s.properties["name"]}
        for c in g.nodes("Component", db)
        for s in g.out(c.id, "SUPPLIED_BY")
    ]


@query(WORK_ORDER_COUNT)
def _work_order_count(g: LocalGraph, db: str) -> Rows:
    return [{"work_orders": g.count("WorkOrder", db)}]


@query(WORK_ORDERS_WITHOUT_FOLLOW_UPS)
def _work_orders_without_follow_ups(g: LocalGraph, db: str) -> Rows:
    missing = sum(1 for w in g.nodes("WorkOrder", db) if not g.out(w.id, "HAS_FOLLOW_UP"))
    return [{"work_orders": missing}]
