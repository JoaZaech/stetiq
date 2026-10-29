"""SQLite metadata store for local mode (in-process, no server)."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from stetiq.errors import KnowledgeGraphAlreadyExistsError
from stetiq.ontology import canonical_json, from_canonical_json
from stetiq.tracking.entities import KnowledgeGraph, OntologyVersion

_SCHEMA = """
CREATE TABLE IF NOT EXISTS knowledge_graphs (
    name        TEXT PRIMARY KEY,
    created_at  TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS ontology_versions (
    knowledge_graph TEXT NOT NULL REFERENCES knowledge_graphs(name),
    number          INTEGER NOT NULL,
    content_hash    TEXT NOT NULL,
    canonical_json  TEXT NOT NULL,
    origin          TEXT NOT NULL,
    created_at      TEXT NOT NULL,
    PRIMARY KEY (knowledge_graph, number),
    UNIQUE (knowledge_graph, content_hash)
);
"""


class SqliteStore:
    def __init__(self, path: str | Path) -> None:
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(path), isolation_level=None)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._conn.executescript(_SCHEMA)
        self._depth = 0

    @contextmanager
    def transaction(self):
        if self._depth == 0:
            self._conn.execute("BEGIN IMMEDIATE")
        self._depth += 1
        try:
            yield
        except BaseException:
            self._depth -= 1
            if self._depth == 0:
                self._conn.execute("ROLLBACK")
            raise
        else:
            self._depth -= 1
            if self._depth == 0:
                self._conn.execute("COMMIT")

    def add_knowledge_graph(self, kg: KnowledgeGraph) -> None:
        try:
            self._conn.execute(
                "INSERT INTO knowledge_graphs (name, created_at) VALUES (?, ?)",
                (kg.name, kg.created_at.isoformat()),
            )
        except sqlite3.IntegrityError:
            raise KnowledgeGraphAlreadyExistsError(
                f"Knowledge Graph {kg.name!r} already exists"
            ) from None

    def get_knowledge_graph(self, name: str) -> KnowledgeGraph | None:
        row = self._conn.execute(
            "SELECT name, created_at FROM knowledge_graphs WHERE name = ?", (name,)
        ).fetchone()
        if row is None:
            return None
        return KnowledgeGraph(name=row["name"], created_at=datetime.fromisoformat(row["created_at"]))

    def add_ontology_version(self, version: OntologyVersion) -> None:
        self._conn.execute(
            "INSERT INTO ontology_versions "
            "(knowledge_graph, number, content_hash, canonical_json, origin, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                version.knowledge_graph,
                version.number,
                version.content_hash,
                canonical_json(version.ontology),
                version.origin,
                version.created_at.isoformat(),
            ),
        )

    def _version_from_row(self, row: sqlite3.Row) -> OntologyVersion:
        return OntologyVersion(
            knowledge_graph=row["knowledge_graph"],
            number=row["number"],
            content_hash=row["content_hash"],
            origin=row["origin"],
            created_at=datetime.fromisoformat(row["created_at"]),
            ontology=from_canonical_json(row["canonical_json"]),
        )

    def get_ontology_version(self, knowledge_graph: str, number: int) -> OntologyVersion | None:
        row = self._conn.execute(
            "SELECT * FROM ontology_versions WHERE knowledge_graph = ? AND number = ?",
            (knowledge_graph, number),
        ).fetchone()
        return None if row is None else self._version_from_row(row)

    def find_ontology_version_by_hash(
        self, knowledge_graph: str, content_hash: str
    ) -> OntologyVersion | None:
        row = self._conn.execute(
            "SELECT * FROM ontology_versions WHERE knowledge_graph = ? AND content_hash = ?",
            (knowledge_graph, content_hash),
        ).fetchone()
        return None if row is None else self._version_from_row(row)

    def list_ontology_versions(self, knowledge_graph: str) -> list[OntologyVersion]:
        rows = self._conn.execute(
            "SELECT * FROM ontology_versions WHERE knowledge_graph = ? ORDER BY number",
            (knowledge_graph,),
        ).fetchall()
        return [self._version_from_row(r) for r in rows]
