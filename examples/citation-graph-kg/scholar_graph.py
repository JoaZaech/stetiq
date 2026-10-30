"""A file-backed stand-in for the university's graph database.

In production the loader writes to Neo4j and stetiq observes it through
`stetiq.graph_source.Neo4jGraphSource`. This example has to run on a laptop with no
services, so `ScholarGraph` keeps the nodes and relationships in one JSON file and
implements stetiq's `GraphSource` protocol:

- `observe(scope)` hands the stored graph to stetiq's own `InMemoryGraphSource`, so the
  Observed Schema (labels, counts, fill rates, cardinalities) is computed the same way
  the real adapters compute it;
- `execute_read(scope, query)` answers the fixed set of Cypher queries the example uses
  (the Competency Questions in use-case.yaml and demo.py, and the queries of the custom
  Evaluator). They are matched by text in `QUERIES`; anything else raises
  `UnsupportedQueryError`, which stetiq records as a failed question by type name only.

The Graph Source lives in the SDK process, next to the loader. The stetiq server never
sees it: only the Observed Schema and Evaluator results travel over HTTP (ADR 0001).
"""

from __future__ import annotations

import json
import re
import unicodedata
from collections import defaultdict
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from stetiq.graph_source import GraphSourceScope, InMemoryGraphSource, ObservedSchema

DEFAULT_DATABASE = "scholar"


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
    """The local store has no implementation for this query text."""


class ScholarGraph:
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
            self._nodes[n["id"]] = Node(n["id"], n["database"], list(n["labels"]), n["properties"])
        for r in data["relationships"]:
            self._relationships.append(Relationship(r["start"], r["type"], r["end"]))

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "nodes": [
                {"id": n.id, "database": n.database, "labels": n.labels, "properties": n.properties}
                for n in self._nodes.values()
            ],
            "relationships": [
                {"start": r.start, "type": r.type, "end": r.end} for r in self._relationships
            ],
        }
        self.path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    # --- writes (the loader's side; stetiq never calls these) -----------------------

    def clear(self, database: str = DEFAULT_DATABASE) -> None:
        """Drop everything in `database`, the way the loader truncates its scope before a rebuild."""
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
        props = {k: v for k, v in (properties or {}).items() if v is not None}
        self._nodes[node_id] = Node(node_id, database, list(labels), props)
        return node_id

    def set_property(self, node_id: int, name: str, value: Any) -> None:
        self._nodes[node_id].properties[name] = value

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

    def in_(self, node_id: int, type_: str) -> list[Node]:
        return [
            self._nodes[r.start]
            for r in self._relationships
            if r.end == node_id and r.type == type_
        ]

    def edges(self, type_: str, database: str = DEFAULT_DATABASE) -> list[tuple[Node, Node]]:
        return [
            (self._nodes[r.start], self._nodes[r.end])
            for r in self._relationships
            if r.type == type_ and self._nodes[r.start].database == database
        ]

    # --- stetiq's GraphSource protocol ----------------------------------------------

    def observe(self, scope: GraphSourceScope) -> ObservedSchema:
        """Reload the file (the loader may run in another process) and let stetiq's
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


# --- The queries the local store can answer ------------------------------------------
#
# Each entry maps the Cypher text (whitespace-normalised) to a function computing the
# same rows over the stored graph. On Neo4j these strings would simply be executed.

Rows = list[dict[str, Any]]
QueryImpl = Callable[[ScholarGraph, str], Rows]
QUERIES: dict[str, QueryImpl] = {}


def _normalise(query: str) -> str:
    return re.sub(r"\s+", " ", query).strip()


def query(text: str) -> Callable[[QueryImpl], QueryImpl]:
    def register(fn: QueryImpl) -> QueryImpl:
        QUERIES[_normalise(text)] = fn
        return fn

    return register


def clean_name(name: str) -> str:
    """What `apoc.text.clean` does: lower-case, strip accents and anything not a letter or digit."""
    decomposed = unicodedata.normalize("NFKD", name)
    return "".join(c for c in decomposed if c.isalnum() and not unicodedata.combining(c)).lower()


PAPERS_PER_AUTHOR = """
MATCH (a:Author)-[:AUTHORED]->(p:Paper)
RETURN a.name AS author, count(p) AS papers ORDER BY papers DESC, author
"""
MOST_CITED_PAPER = """
MATCH (p:Paper)<-[:CITES]-(c:Paper)
RETURN p.doi AS doi, count(c) AS citations ORDER BY citations DESC LIMIT 1
"""
GRANT_FUNDED_PAPERS = """
MATCH (p:Paper)-[:FUNDED_BY]->(g:Grant)
RETURN g.id AS grant, count(p) AS papers ORDER BY papers DESC, grant
"""
CO_AUTHORSHIP_PAIRS = """
MATCH (a:Author)-[:AUTHORED]->(:Paper)<-[:AUTHORED]-(b:Author) WHERE a.name < b.name
RETURN a.name AS author, b.name AS co_author, count(*) AS papers ORDER BY papers DESC, author, co_author
"""
VENUES_BY_YEAR = """
MATCH (p:Paper)-[:PUBLISHED_IN]->(v:Venue)
RETURN p.year AS year, v.name AS venue, count(p) AS papers ORDER BY year, venue
"""
# Author identity is the ORCID iD, not the spelling of a name: a self-citation is a
# citing and a cited paper that share an ORCID-verified author.
SELF_CITATION_SHARE = """
MATCH (p:Paper)-[:CITES]->(q:Paper)
WITH p, q, exists { MATCH (a:Author)-[:AUTHORED]->(p) WHERE a.orcid IS NOT NULL AND (a)-[:AUTHORED]->(q) } AS self_citation
RETURN count(*) AS citations, sum(CASE WHEN self_citation THEN 1 ELSE 0 END) AS self_citations
"""
ORCID_COAUTHORS = """
MATCH (a:Author)-[:CO_AUTHORED]->(b:Author) WHERE a.orcid IS NOT NULL AND b.orcid IS NOT NULL
RETURN a.name AS author, b.name AS co_author ORDER BY author, co_author
"""
AUTHOR_COUNT = "MATCH (a:Author) RETURN count(a) AS authors"
DUPLICATE_AUTHORS = """
MATCH (a:Author)
WITH apoc.text.clean(a.name) AS key, count(a) AS spellings WHERE spellings > 1
RETURN count(key) AS duplicate_groups, sum(spellings) - count(key) AS duplicate_authors
"""


@query(PAPERS_PER_AUTHOR)
def _papers_per_author(g: ScholarGraph, db: str) -> Rows:
    rows = [
        {"author": a.properties["name"], "papers": len(g.out(a.id, "AUTHORED"))}
        for a in g.nodes("Author", db)
        if g.out(a.id, "AUTHORED")
    ]
    return sorted(rows, key=lambda r: (-r["papers"], r["author"]))


@query(MOST_CITED_PAPER)
def _most_cited_paper(g: ScholarGraph, db: str) -> Rows:
    rows = [
        {"doi": p.properties["doi"], "citations": len(g.in_(p.id, "CITES"))}
        for p in g.nodes("Paper", db)
        if g.in_(p.id, "CITES")
    ]
    rows.sort(key=lambda r: (-r["citations"], r["doi"]))
    return rows[:1]


@query(GRANT_FUNDED_PAPERS)
def _grant_funded_papers(g: ScholarGraph, db: str) -> Rows:
    rows = [
        {"grant": grant.properties["id"], "papers": len(g.in_(grant.id, "FUNDED_BY"))}
        for grant in g.nodes("Grant", db)
        if g.in_(grant.id, "FUNDED_BY")
    ]
    return sorted(rows, key=lambda r: (-r["papers"], r["grant"]))


@query(CO_AUTHORSHIP_PAIRS)
def _co_authorship_pairs(g: ScholarGraph, db: str) -> Rows:
    counts: dict[tuple[str, str], int] = defaultdict(int)
    for p in g.nodes("Paper", db):
        names = sorted(a.properties["name"] for a in g.in_(p.id, "AUTHORED"))
        for i, a in enumerate(names):
            for b in names[i + 1 :]:
                if a < b:
                    counts[(a, b)] += 1
    return [
        {"author": a, "co_author": b, "papers": n}
        for (a, b), n in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    ]


@query(VENUES_BY_YEAR)
def _venues_by_year(g: ScholarGraph, db: str) -> Rows:
    counts: dict[tuple[int, str], int] = defaultdict(int)
    for p in g.nodes("Paper", db):
        for v in g.out(p.id, "PUBLISHED_IN"):
            counts[(p.properties["year"], v.properties["name"])] += 1
    return [
        {"year": year, "venue": venue, "papers": n} for (year, venue), n in sorted(counts.items())
    ]


@query(SELF_CITATION_SHARE)
def _self_citation_share(g: ScholarGraph, db: str) -> Rows:
    def verified_authors(paper: Node) -> set[int]:
        return {a.id for a in g.in_(paper.id, "AUTHORED") if a.properties.get("orcid")}

    edges = g.edges("CITES", db)
    self_citations = sum(1 for p, q in edges if verified_authors(p) & verified_authors(q))
    return [{"citations": len(edges), "self_citations": self_citations}]


@query(ORCID_COAUTHORS)
def _orcid_coauthors(g: ScholarGraph, db: str) -> Rows:
    rows = [
        {"author": a.properties["name"], "co_author": b.properties["name"]}
        for a, b in g.edges("CO_AUTHORED", db)
        if a.properties.get("orcid") and b.properties.get("orcid")
    ]
    return sorted(rows, key=lambda r: (r["author"], r["co_author"]))


@query(AUTHOR_COUNT)
def _author_count(g: ScholarGraph, db: str) -> Rows:
    return [{"authors": len(g.nodes("Author", db))}]


@query(DUPLICATE_AUTHORS)
def _duplicate_authors(g: ScholarGraph, db: str) -> Rows:
    spellings: dict[str, int] = defaultdict(int)
    for a in g.nodes("Author", db):
        spellings[clean_name(a.properties["name"])] += 1
    groups = [n for n in spellings.values() if n > 1]
    return [{"duplicate_groups": len(groups), "duplicate_authors": sum(groups) - len(groups)}]
