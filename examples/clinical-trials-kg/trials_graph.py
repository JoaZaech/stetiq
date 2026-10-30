"""A file-backed stand-in for the registry's graph database.

In production the loader writes to Neo4j and stetiq observes it through
`stetiq.graph_source.Neo4jGraphSource`. This example runs on a laptop with no
services, so `RegistryGraph` keeps nodes and relationships in one JSON file and
implements stetiq's `GraphSource` protocol:

- `observe(scope)` hands the stored graph to stetiq's own `InMemoryGraphSource`, so the
  Observed Schema (labels, counts, fill rates, cardinalities) is computed the way the
  real adapters compute it;
- `execute_read(scope, query)` answers the fixed set of Cypher queries the example uses
  (the Competency Questions in use-case.yaml and the counts of the `consent_coverage`
  Evaluator), matched by text in `QUERIES`. Anything else raises
  `UnsupportedQueryError`, which stetiq records as a failed question by type name only.

Only the loader writes. stetiq reads, and only aggregates leave this process (ADR 0001):
no pseudonym, visit or adverse event ever reaches the tracking database.
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

DEFAULT_DATABASE = "registry"


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


class UnsupportedQueryError(Exception):
    """The local graph database file has no implementation for this query text."""


class RegistryGraph:
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

    # --- writes (the loader's side; stetiq never calls these) -----------------------

    def clear(self, database: str = DEFAULT_DATABASE) -> None:
        """Drop everything in `database`: the loader rebuilds its scope from the export."""
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

    def add_relationship(self, start: int, type_: str, end: int) -> None:
        self._relationships.append(Relationship(start, type_, end))

    # --- reads used by the query implementations ------------------------------------

    def nodes(self, label: str, database: str = DEFAULT_DATABASE) -> list[Node]:
        return [n for n in self._nodes.values() if n.database == database and label in n.labels]

    def out(self, node_id: int, type_: str) -> list[Node]:
        return [
            self._nodes[r.end]
            for r in self._relationships
            if r.start == node_id and r.type == type_
        ]

    def count(self, label: str, database: str = DEFAULT_DATABASE) -> int:
        return len(self.nodes(label, database))

    # --- stetiq's GraphSource protocol ----------------------------------------------

    def observe(self, scope: GraphSourceScope) -> ObservedSchema:
        """Reload the file (the loader runs in another process) and let stetiq's
        in-memory adapter compute the Observed Schema."""
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


# --- The queries the local graph database file can answer -----------------------------
#
# Each entry maps the Cypher text (whitespace-normalised) to a function computing the
# same rows over the stored graph. On Neo4j these strings would simply be executed.

Rows = list[dict[str, Any]]
QueryImpl = Callable[[RegistryGraph, str], Rows]
QUERIES: dict[str, QueryImpl] = {}


def _normalise(query: str) -> str:
    return re.sub(r"\s+", " ", query).strip()


def query(text: str) -> Callable[[QueryImpl], QueryImpl]:
    def register(fn: QueryImpl) -> QueryImpl:
        QUERIES[_normalise(text)] = fn
        return fn

    return register


SERIOUS_EVENTS_PER_TRIAL = """
MATCH (a:AdverseEvent {serious: true})-[:REPORTED_IN]->(t:Trial)
RETURN t.registry_id AS trial, count(a) AS serious_events ORDER BY trial
"""
PARTICIPANTS_PER_SITE = """
MATCH (p:Participant)-[:ENROLLED_AT]->(s:Site)
RETURN s.site_id AS site, count(p) AS participants ORDER BY participants DESC, site
"""
DRUGS_UNDER_TEST = """
MATCH (t:Trial)-[:TESTS]->(d:Drug)
RETURN d.name AS drug, count(t) AS trials ORDER BY drug
"""
PROTOCOL_DEVIATIONS = """
MATCH (p:Participant)-[:ATTENDED]->(v:Visit) WHERE v.deviation IS NOT NULL
RETURN v.deviation AS deviation, count(v) AS visits ORDER BY visits DESC, deviation
"""
SITE_INVESTIGATORS = """
MATCH (s:Site)-[:LED_BY]->(i:Investigator)
RETURN s.site_id AS site, i.staff_id AS investigator ORDER BY site
"""
CONDITIONS_STUDIED = """
MATCH (t:Trial)-[:STUDIES]->(c:Condition)
RETURN c.code AS condition, count(t) AS trials ORDER BY condition
"""
EVENTS_PER_ARM = """
MATCH (p:Participant)-[:ASSIGNED_TO]->(a:Arm) MATCH (p)-[:EXPERIENCED]->(e:AdverseEvent)
RETURN a.code AS arm, count(e) AS events ORDER BY arm
"""
PARTICIPANT_COUNT = "MATCH (p:Participant) RETURN count(p) AS participants"
PARTICIPANTS_WITHOUT_CONSENT = """
MATCH (p:Participant) WHERE NOT (p)-[:CONSENTED_TO]->(:Trial)
RETURN count(p) AS participants
"""


def _counted(counts: dict[str, int], key: str, value: str, *, by_count: bool = False) -> Rows:
    order = (lambda kv: (-kv[1], kv[0])) if by_count else (lambda kv: kv[0])
    return [{key: k, value: n} for k, n in sorted(counts.items(), key=order)]


@query(SERIOUS_EVENTS_PER_TRIAL)
def _serious_events_per_trial(g: RegistryGraph, db: str) -> Rows:
    counts: dict[str, int] = defaultdict(int)
    for a in g.nodes("AdverseEvent", db):
        if a.properties.get("serious") is True:
            for t in g.out(a.id, "REPORTED_IN"):
                counts[t.properties["registry_id"]] += 1
    return _counted(counts, "trial", "serious_events")


@query(PARTICIPANTS_PER_SITE)
def _participants_per_site(g: RegistryGraph, db: str) -> Rows:
    counts: dict[str, int] = defaultdict(int)
    for p in g.nodes("Participant", db):
        for s in g.out(p.id, "ENROLLED_AT"):
            counts[s.properties["site_id"]] += 1
    return _counted(counts, "site", "participants", by_count=True)


@query(DRUGS_UNDER_TEST)
def _drugs_under_test(g: RegistryGraph, db: str) -> Rows:
    counts: dict[str, int] = defaultdict(int)
    for t in g.nodes("Trial", db):
        for d in g.out(t.id, "TESTS"):
            if "Drug" in d.labels:
                counts[d.properties["name"]] += 1
    return _counted(counts, "drug", "trials")


@query(PROTOCOL_DEVIATIONS)
def _protocol_deviations(g: RegistryGraph, db: str) -> Rows:
    counts: dict[str, int] = defaultdict(int)
    for p in g.nodes("Participant", db):
        for v in g.out(p.id, "ATTENDED"):
            if v.properties.get("deviation") is not None:
                counts[v.properties["deviation"]] += 1
    return _counted(counts, "deviation", "visits", by_count=True)


@query(SITE_INVESTIGATORS)
def _site_investigators(g: RegistryGraph, db: str) -> Rows:
    return sorted(
        (
            {"site": s.properties["site_id"], "investigator": i.properties["staff_id"]}
            for s in g.nodes("Site", db)
            for i in g.out(s.id, "LED_BY")
        ),
        key=lambda r: r["site"],
    )


@query(CONDITIONS_STUDIED)
def _conditions_studied(g: RegistryGraph, db: str) -> Rows:
    counts: dict[str, int] = defaultdict(int)
    for t in g.nodes("Trial", db):
        for c in g.out(t.id, "STUDIES"):
            counts[c.properties["code"]] += 1
    return _counted(counts, "condition", "trials")


@query(EVENTS_PER_ARM)
def _events_per_arm(g: RegistryGraph, db: str) -> Rows:
    counts: dict[str, int] = defaultdict(int)
    for p in g.nodes("Participant", db):
        events = g.out(p.id, "EXPERIENCED")
        for a in g.out(p.id, "ASSIGNED_TO"):
            counts[a.properties["code"]] += len(events)
    return _counted(counts, "arm", "events")


@query(PARTICIPANT_COUNT)
def _participant_count(g: RegistryGraph, db: str) -> Rows:
    return [{"participants": g.count("Participant", db)}]


@query(PARTICIPANTS_WITHOUT_CONSENT)
def _participants_without_consent(g: RegistryGraph, db: str) -> Rows:
    missing = sum(1 for p in g.nodes("Participant", db) if not g.out(p.id, "CONSENTED_TO"))
    return [{"participants": missing}]
