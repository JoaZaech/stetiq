"""SQL metadata store (SQLAlchemy Core): SQLite for local mode, SQLite or Postgres for the server.

`SqlStore(database_url)` takes a SQLAlchemy URL:
- `sqlite:///<path>` (or `sqlite:///:memory:`)
- `postgresql+psycopg://user@host/db` (install the `stetiq[postgres]` extra); a bare
  `postgresql://` URL is mapped to the psycopg 3 driver.

Tables are created on first use. The schema matches the original stdlib-sqlite
store, so existing `.stetiq/stetiq.db` files keep working.
"""

from __future__ import annotations

import threading
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from sqlalchemy import (
    Column,
    Connection,
    ForeignKey,
    Integer,
    MetaData,
    PrimaryKeyConstraint,
    Table,
    Text,
    UniqueConstraint,
    create_engine,
    event,
    insert,
    select,
)
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError
from sqlalchemy.pool import StaticPool

from stetiq.errors import KnowledgeGraphAlreadyExistsError
from stetiq.ontology import canonical_json, from_canonical_json
from stetiq.tracking.entities import KnowledgeGraph, OntologyVersion

metadata = MetaData()

knowledge_graphs = Table(
    "knowledge_graphs",
    metadata,
    Column("name", Text, primary_key=True),
    Column("created_at", Text, nullable=False),  # ISO-8601, UTC
)

ontology_versions = Table(
    "ontology_versions",
    metadata,
    Column("knowledge_graph", Text, ForeignKey("knowledge_graphs.name"), nullable=False),
    Column("number", Integer, nullable=False),
    Column("content_hash", Text, nullable=False),
    Column("canonical_json", Text, nullable=False),
    Column("origin", Text, nullable=False),
    Column("created_at", Text, nullable=False),
    PrimaryKeyConstraint("knowledge_graph", "number"),
    UniqueConstraint("knowledge_graph", "content_hash"),
)


def _engine(database_url: str):
    url = make_url(database_url)
    if url.drivername == "postgresql":
        url = url.set(drivername="postgresql+psycopg")
    if not url.drivername.startswith("sqlite"):
        return create_engine(url)

    if url.database and url.database != ":memory:":
        Path(url.database).parent.mkdir(parents=True, exist_ok=True)
        engine = create_engine(url, connect_args={"check_same_thread": False})
    else:
        # One shared connection, or every pooled connection would see its own empty DB.
        engine = create_engine(
            url, poolclass=StaticPool, connect_args={"check_same_thread": False}
        )

    # pysqlite's own transaction handling is off; we emit BEGIN IMMEDIATE so a
    # transaction takes the write lock up front (no lost-update on numbering).
    @event.listens_for(engine, "connect")
    def _on_connect(dbapi_conn, _record):
        dbapi_conn.isolation_level = None
        dbapi_conn.execute("PRAGMA foreign_keys = ON")

    @event.listens_for(engine, "begin")
    def _on_begin(conn):
        conn.exec_driver_sql("BEGIN IMMEDIATE")

    return engine


class SqlStore:
    def __init__(self, database_url: str) -> None:
        self._engine = _engine(database_url)
        self._local = threading.local()  # the open transaction's connection, per thread
        metadata.create_all(self._engine)

    def drop_all(self) -> None:
        """Delete every table (test helper); they are recreated on next construction."""
        metadata.drop_all(self._engine)

    @contextmanager
    def transaction(self) -> Iterator[None]:
        if getattr(self._local, "conn", None) is not None:
            yield  # nested: join the outer transaction
            return
        with self._engine.begin() as conn:
            self._local.conn = conn
            try:
                yield
            finally:
                self._local.conn = None

    @contextmanager
    def _connection(self) -> Iterator[Connection]:
        conn = getattr(self._local, "conn", None)
        if conn is not None:
            yield conn
        else:
            with self._engine.begin() as conn:
                yield conn

    def add_knowledge_graph(self, kg: KnowledgeGraph) -> None:
        with self._connection() as conn:
            try:
                with conn.begin_nested():
                    conn.execute(
                        insert(knowledge_graphs).values(
                            name=kg.name, created_at=kg.created_at.isoformat()
                        )
                    )
            except IntegrityError:
                raise KnowledgeGraphAlreadyExistsError(
                    f"Knowledge Graph {kg.name!r} already exists"
                ) from None

    def get_knowledge_graph(self, name: str) -> KnowledgeGraph | None:
        query = select(knowledge_graphs).where(knowledge_graphs.c.name == name)
        if getattr(self._local, "conn", None) is not None:
            # Inside a transaction, lock the row: concurrent registrations on the same
            # Knowledge Graph serialise (Postgres; SQLite already holds the write lock).
            query = query.with_for_update()
        with self._connection() as conn:
            row = conn.execute(query).mappings().first()
        if row is None:
            return None
        return KnowledgeGraph(name=row["name"], created_at=datetime.fromisoformat(row["created_at"]))

    def add_ontology_version(self, version: OntologyVersion) -> None:
        with self._connection() as conn:
            conn.execute(
                insert(ontology_versions).values(
                    knowledge_graph=version.knowledge_graph,
                    number=version.number,
                    content_hash=version.content_hash,
                    canonical_json=canonical_json(version.ontology),
                    origin=version.origin,
                    created_at=version.created_at.isoformat(),
                )
            )

    def _one_version(self, *where) -> OntologyVersion | None:
        with self._connection() as conn:
            row = conn.execute(select(ontology_versions).where(*where)).mappings().first()
        return None if row is None else _version_from_row(row)

    def get_ontology_version(self, knowledge_graph: str, number: int) -> OntologyVersion | None:
        return self._one_version(
            ontology_versions.c.knowledge_graph == knowledge_graph,
            ontology_versions.c.number == number,
        )

    def find_ontology_version_by_hash(
        self, knowledge_graph: str, content_hash: str
    ) -> OntologyVersion | None:
        return self._one_version(
            ontology_versions.c.knowledge_graph == knowledge_graph,
            ontology_versions.c.content_hash == content_hash,
        )

    def list_ontology_versions(self, knowledge_graph: str) -> list[OntologyVersion]:
        query = (
            select(ontology_versions)
            .where(ontology_versions.c.knowledge_graph == knowledge_graph)
            .order_by(ontology_versions.c.number)
        )
        with self._connection() as conn:
            rows = conn.execute(query).mappings().all()
        return [_version_from_row(r) for r in rows]


def _version_from_row(row) -> OntologyVersion:
    return OntologyVersion(
        knowledge_graph=row["knowledge_graph"],
        number=row["number"],
        content_hash=row["content_hash"],
        origin=row["origin"],
        created_at=datetime.fromisoformat(row["created_at"]),
        ontology=from_canonical_json(row["canonical_json"]),
    )
