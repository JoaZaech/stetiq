"""A file-backed stand-in for the transit operator's graph database.

In production the pipeline writes to Neo4j and stetiq observes it through
`stetiq.graph_source.Neo4jGraphSource`, configured by `STETIQ_GRAPH_SOURCE_URI`. This
example has to run on a laptop with no services, so `TransitGraph` keeps the nodes and
relationships in one JSON file and implements stetiq's `GraphSource` protocol:

- `observe(scope)` hands the stored graph to stetiq's own `InMemoryGraphSource`, so
  the Observed Schema (labels, counts, fill rates, cardinalities) is computed the same
  way the real adapters compute it;
- `execute_read(scope, query)` answers the fixed set of Cypher queries the example
  uses (the Competency Questions in use-case.yaml). They are matched by text in
  `QUERIES`; anything else raises `UnsupportedQueryError`, which stetiq records as a
  failed question by exception type only.

The pipeline (transit_pipeline.py) and the demo's "someone edited the database by
hand" step use the write methods. stetiq itself never writes.
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

DEFAULT_DATABASE = "transit"


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


class TransitGraph:
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
            self._relationships.append(Relationship(r["start"], r["type"], r["end"]))

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
                {"start": r.start, "type": r.type, "end": r.end} for r in self._relationships
            ],
        }
        self.path.write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")

    # --- writes (the pipeline's side; stetiq never calls these) ---------------------

    def clear(self, database: str = DEFAULT_DATABASE) -> None:
        """Drop everything in `database`, the way the pipeline truncates its scope before a rebuild."""
        gone = {n.id for n in self._nodes.values() if n.database == database}
        self._delete(gone)

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

    def add_relationship(self, start: int, type_: str, end: int) -> None:
        self._relationships.append(Relationship(start, type_, end))

    def delete_nodes(self, ids: Iterable[int]) -> int:
        """Delete these nodes and every relationship touching them."""
        gone = set(ids) & set(self._nodes)
        self._delete(gone)
        return len(gone)

    def _delete(self, gone: set[int]) -> None:
        self._nodes = {i: n for i, n in self._nodes.items() if i not in gone}
        self._relationships = [
            r for r in self._relationships if r.start not in gone and r.end not in gone
        ]

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
        """Reload the file (the pipeline process may have written it) and let stetiq's
        in-memory adapter compute the Observed Schema. Only aggregates leave here."""
        self.load()
        memory = InMemoryGraphSource()
        ids: dict[int, int] = {}
        for node in self._nodes.values():
            ids[node.id] = memory.add_node(node.labels, node.properties, database=node.database)
        for rel in self._relationships:
            memory.add_relationship(ids[rel.start], rel.type, ids[rel.end])
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
QueryImpl = Callable[[TransitGraph, str], Rows]
QUERIES: dict[str, QueryImpl] = {}


def _normalise(query: str) -> str:
    return re.sub(r"\s+", " ", query).strip()


def query(text: str) -> Callable[[QueryImpl], QueryImpl]:
    def register(fn: QueryImpl) -> QueryImpl:
        QUERIES[_normalise(text)] = fn
        return fn

    return register


STOPS_ON_ROUTE = """
MATCH (r:Route {short_name: '1'})-[:HAS_TRIP]->(:Trip)-[:HAS_STOP_TIME]->(:StopTime)-[:AT_STOP]->(s:Stop)
RETURN DISTINCT s.name AS stop ORDER BY stop
"""
TRANSFERS_AT_STOP = """
MATCH (s:Stop {name: 'Market Square'})<-[:AT_STOP]-(:StopTime)<-[:HAS_STOP_TIME]-(:Trip)<-[:HAS_TRIP]-(r:Route)
RETURN DISTINCT r.short_name AS route ORDER BY route
"""
TRIPS_PER_SERVICE = """
MATCH (t:Trip)-[:RUNS_ON]->(c:Service)
RETURN c.id AS service, count(t) AS trips ORDER BY service
"""
ACCESSIBLE_STOPS = """
MATCH (s:Stop) WHERE s.wheelchair_boarding IS NOT NULL
RETURN s.wheelchair_boarding AS wheelchair_boarding, count(s) AS stops ORDER BY wheelchair_boarding
"""
STOPS_PER_ZONE = """
MATCH (s:Stop)-[:IN_ZONE]->(z:FareZone)
RETURN z.name AS zone, count(s) AS stops ORDER BY zone
"""


def _routes_of_stop(g: TransitGraph, stop: Node) -> set[str]:
    return {
        r.properties["short_name"]
        for call in g.in_(stop.id, "AT_STOP")
        for trip in g.in_(call.id, "HAS_STOP_TIME")
        for r in g.in_(trip.id, "HAS_TRIP")
    }


@query(STOPS_ON_ROUTE)
def _stops_on_route(g: TransitGraph, db: str) -> Rows:
    route = g.find("Route", db, short_name="1")
    if route is None:
        return []
    names = {
        stop.properties["name"]
        for trip in g.out(route.id, "HAS_TRIP")
        for call in g.out(trip.id, "HAS_STOP_TIME")
        for stop in g.out(call.id, "AT_STOP")
    }
    return [{"stop": name} for name in sorted(names)]


@query(TRANSFERS_AT_STOP)
def _transfers_at_stop(g: TransitGraph, db: str) -> Rows:
    stop = g.find("Stop", db, name="Market Square")
    if stop is None:
        return []
    return [{"route": route} for route in sorted(_routes_of_stop(g, stop))]


@query(TRIPS_PER_SERVICE)
def _trips_per_service(g: TransitGraph, db: str) -> Rows:
    counts: dict[str, int] = defaultdict(int)
    for trip in g.nodes("Trip", db):
        for service in g.out(trip.id, "RUNS_ON"):
            counts[service.properties["id"]] += 1
    return [{"service": s, "trips": n} for s, n in sorted(counts.items())]


@query(ACCESSIBLE_STOPS)
def _accessible_stops(g: TransitGraph, db: str) -> Rows:
    counts: dict[int, int] = defaultdict(int)
    for stop in g.nodes("Stop", db):
        value = stop.properties.get("wheelchair_boarding")
        if value is not None:
            counts[value] += 1
    return [{"wheelchair_boarding": v, "stops": n} for v, n in sorted(counts.items())]


@query(STOPS_PER_ZONE)
def _stops_per_zone(g: TransitGraph, db: str) -> Rows:
    counts: dict[str, int] = defaultdict(int)
    for stop in g.nodes("Stop", db):
        for zone in g.out(stop.id, "IN_ZONE"):
            counts[zone.properties["name"]] += 1
    return [{"zone": z, "stops": n} for z, n in sorted(counts.items())]
