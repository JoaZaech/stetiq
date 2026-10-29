"""SQL metadata store (SQLAlchemy Core): SQLite for local mode, SQLite or Postgres for the server.

`SqlStore(database_url)` takes a SQLAlchemy URL:
- `sqlite:///<path>` (or `sqlite:///:memory:`)
- `postgresql+psycopg://user@host/db` (install the `stetiq[postgres]` extra); a bare
  `postgresql://` URL is mapped to the psycopg 3 driver.

Tables are created on first use. The schema matches the original stdlib-sqlite
store, so existing `.stetiq/stetiq.db` files keep working.
"""

from __future__ import annotations

import json
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from sqlalchemy import (
    Column,
    Connection,
    Float,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    MetaData,
    PrimaryKeyConstraint,
    Table,
    Text,
    UniqueConstraint,
    create_engine,
    delete,
    event,
    insert,
    select,
    update,
)
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError
from sqlalchemy.pool import StaticPool

from stetiq.errors import KnowledgeGraphAlreadyExistsError
from stetiq.graph_source import GraphSourceScope, ObservedSchema
from stetiq.ontology import canonical_json, from_canonical_json
from stetiq.evaluation.framework import Detail
from stetiq.tracking.entities import (
    ConstructionRun,
    EvaluationResult,
    KnowledgeGraph,
    Observation,
    OntologyVersion,
    RunStatus,
)

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

# One Graph Source scope per Knowledge Graph (no credentials: those stay with the adapter).
graph_sources = Table(
    "graph_sources",
    metadata,
    Column("knowledge_graph", Text, ForeignKey("knowledge_graphs.name"), primary_key=True),
    Column("database", Text, nullable=False),
    Column("label", Text, nullable=True),
    Column("namespace", Text, nullable=True),
)

construction_runs = Table(
    "construction_runs",
    metadata,
    Column("id", Text, primary_key=True),
    Column("knowledge_graph", Text, ForeignKey("knowledge_graphs.name"), nullable=False),
    Column("ontology_version", Integer, nullable=False),
    Column("status", Text, nullable=False),  # running | finished | failed
    Column("started_at", Text, nullable=False),
    Column("ended_at", Text, nullable=True),
    Column("observation_id", Text, nullable=True),
    ForeignKeyConstraint(
        ["knowledge_graph", "ontology_version"],
        ["ontology_versions.knowledge_graph", "ontology_versions.number"],
    ),
)

run_params = Table(
    "run_params",
    metadata,
    Column("run_id", Text, ForeignKey("construction_runs.id"), nullable=False),
    Column("key", Text, nullable=False),
    Column("value", Text, nullable=False),
    PrimaryKeyConstraint("run_id", "key"),
)

run_metrics = Table(
    "run_metrics",
    metadata,
    Column("run_id", Text, ForeignKey("construction_runs.id"), nullable=False),
    Column("key", Text, nullable=False),
    Column("value", Float, nullable=False),
    PrimaryKeyConstraint("run_id", "key"),
)

# Observed Schemas hold structure and aggregate statistics only (ADR 0001).
observations = Table(
    "observations",
    metadata,
    Column("id", Text, primary_key=True),
    Column("knowledge_graph", Text, ForeignKey("knowledge_graphs.name"), nullable=False),
    Column("run_id", Text, ForeignKey("construction_runs.id"), nullable=True),
    Column("observed_at", Text, nullable=False),
    Column("scope_json", Text, nullable=False),
    Column("schema_json", Text, nullable=False),
)


# Insert-only: a re-run adds rows; readers take the latest row per evaluator.
evaluation_results = Table(
    "evaluation_results",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("knowledge_graph", Text, ForeignKey("knowledge_graphs.name"), nullable=False),
    Column("subject_kind", Text, nullable=False),  # "ontology_version" | "construction_run"
    Column("subject_id", Text, nullable=False),  # version number as text, or run id
    Column("evaluator", Text, nullable=False),
    Column("metrics_json", Text, nullable=False),
    Column("details_json", Text, nullable=False),
    Column("created_at", Text, nullable=False),
)
Index(
    "ix_evaluation_results_subject",
    evaluation_results.c.knowledge_graph,
    evaluation_results.c.subject_kind,
    evaluation_results.c.subject_id,
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

    # --- Graph Source binding -------------------------------------------------------

    def set_graph_source(self, knowledge_graph: str, scope: GraphSourceScope) -> None:
        with self._connection() as conn:
            conn.execute(
                delete(graph_sources).where(graph_sources.c.knowledge_graph == knowledge_graph)
            )
            conn.execute(
                insert(graph_sources).values(knowledge_graph=knowledge_graph, **scope.to_dict())
            )

    def get_graph_source(self, knowledge_graph: str) -> GraphSourceScope | None:
        query = select(graph_sources).where(graph_sources.c.knowledge_graph == knowledge_graph)
        with self._connection() as conn:
            row = conn.execute(query).mappings().first()
        return None if row is None else GraphSourceScope.from_dict(dict(row))

    # --- Construction Runs ----------------------------------------------------------

    def add_run(self, run: ConstructionRun) -> None:
        with self._connection() as conn:
            conn.execute(
                insert(construction_runs).values(
                    id=run.id,
                    knowledge_graph=run.knowledge_graph,
                    ontology_version=run.ontology_version,
                    status=run.status,
                    started_at=run.started_at.isoformat(),
                    ended_at=None if run.ended_at is None else run.ended_at.isoformat(),
                    observation_id=run.observation_id,
                )
            )
        self.set_run_params(run.id, run.params)
        self.set_run_metrics(run.id, run.metrics)

    def _runs(self, *where) -> list[ConstructionRun]:
        query = (
            select(construction_runs)
            .where(*where)
            .order_by(construction_runs.c.started_at, construction_runs.c.id)
        )
        with self._connection() as conn:
            rows = conn.execute(query).mappings().all()
            ids = [r["id"] for r in rows]
            params: dict[str, dict[str, str]] = {i: {} for i in ids}
            metrics: dict[str, dict[str, float]] = {i: {} for i in ids}
            if ids:
                for p in conn.execute(select(run_params).where(run_params.c.run_id.in_(ids))):
                    params[p.run_id][p.key] = p.value
                for m in conn.execute(select(run_metrics).where(run_metrics.c.run_id.in_(ids))):
                    metrics[m.run_id][m.key] = m.value
        return [
            ConstructionRun(
                id=r["id"],
                knowledge_graph=r["knowledge_graph"],
                ontology_version=r["ontology_version"],
                status=r["status"],
                started_at=datetime.fromisoformat(r["started_at"]),
                ended_at=None if r["ended_at"] is None else datetime.fromisoformat(r["ended_at"]),
                params=params[r["id"]],
                metrics=metrics[r["id"]],
                observation_id=r["observation_id"],
            )
            for r in rows
        ]

    def get_run(self, run_id: str) -> ConstructionRun | None:
        runs = self._runs(construction_runs.c.id == run_id)
        return runs[0] if runs else None

    def list_runs(self, knowledge_graph: str) -> list[ConstructionRun]:
        return self._runs(construction_runs.c.knowledge_graph == knowledge_graph)

    def _upsert(self, table: Table, run_id: str, values: dict) -> None:
        if not values:
            return
        with self._connection() as conn:
            conn.execute(
                delete(table).where(table.c.run_id == run_id, table.c.key.in_(list(values)))
            )
            conn.execute(
                insert(table), [{"run_id": run_id, "key": k, "value": v} for k, v in values.items()]
            )

    def set_run_params(self, run_id: str, params: dict[str, str]) -> None:
        self._upsert(run_params, run_id, params)

    def set_run_metrics(self, run_id: str, metrics: dict[str, float]) -> None:
        self._upsert(run_metrics, run_id, metrics)

    def end_run(
        self, run_id: str, status: RunStatus, ended_at: datetime, observation_id: str | None
    ) -> None:
        with self._connection() as conn:
            conn.execute(
                update(construction_runs)
                .where(construction_runs.c.id == run_id)
                .values(
                    status=status, ended_at=ended_at.isoformat(), observation_id=observation_id
                )
            )

    # --- Observations ---------------------------------------------------------------

    def add_observation(self, observation: Observation) -> None:
        with self._connection() as conn:
            conn.execute(
                insert(observations).values(
                    id=observation.id,
                    knowledge_graph=observation.knowledge_graph,
                    run_id=observation.run_id,
                    observed_at=observation.observed_at.isoformat(),
                    scope_json=json.dumps(observation.scope.to_dict(), sort_keys=True),
                    schema_json=json.dumps(observation.schema.to_dict(), sort_keys=True),
                )
            )

    def _observations(self, *where) -> list[Observation]:
        query = (
            select(observations)
            .where(*where)
            .order_by(observations.c.observed_at, observations.c.id)
        )
        with self._connection() as conn:
            rows = conn.execute(query).mappings().all()
        return [
            Observation(
                id=r["id"],
                knowledge_graph=r["knowledge_graph"],
                scope=GraphSourceScope.from_dict(json.loads(r["scope_json"])),
                observed_at=datetime.fromisoformat(r["observed_at"]),
                schema=ObservedSchema.from_dict(json.loads(r["schema_json"])),
                run_id=r["run_id"],
            )
            for r in rows
        ]

    def get_observation(self, observation_id: str) -> Observation | None:
        found = self._observations(observations.c.id == observation_id)
        return found[0] if found else None

    def list_observations(self, knowledge_graph: str) -> list[Observation]:
        return self._observations(observations.c.knowledge_graph == knowledge_graph)

    def add_evaluation_result(self, result: EvaluationResult) -> None:
        with self._connection() as conn:
            conn.execute(
                insert(evaluation_results).values(
                    knowledge_graph=result.knowledge_graph,
                    subject_kind=result.subject_kind,
                    subject_id=result.subject_id,
                    evaluator=result.evaluator,
                    metrics_json=json.dumps(result.metrics, sort_keys=True),
                    details_json=json.dumps(
                        [
                            {"item": d.item, "message": d.message, "metric": d.metric}
                            for d in result.details
                        ]
                    ),
                    created_at=result.created_at.isoformat(),
                )
            )

    def list_evaluation_results(
        self, knowledge_graph: str, subject_kind: str, subject_id: str
    ) -> list[EvaluationResult]:
        query = (
            select(evaluation_results)
            .where(
                evaluation_results.c.knowledge_graph == knowledge_graph,
                evaluation_results.c.subject_kind == subject_kind,
                evaluation_results.c.subject_id == subject_id,
            )
            .order_by(evaluation_results.c.id)
        )
        with self._connection() as conn:
            rows = conn.execute(query).mappings().all()
        return [_evaluation_from_row(r) for r in rows]


def _evaluation_from_row(row) -> EvaluationResult:
    return EvaluationResult(
        knowledge_graph=row["knowledge_graph"],
        subject_kind=row["subject_kind"],
        subject_id=row["subject_id"],
        evaluator=row["evaluator"],
        metrics=json.loads(row["metrics_json"]),
        details=tuple(Detail(**d) for d in json.loads(row["details_json"])),
        created_at=datetime.fromisoformat(row["created_at"]),
    )


def _version_from_row(row) -> OntologyVersion:
    return OntologyVersion(
        knowledge_graph=row["knowledge_graph"],
        number=row["number"],
        content_hash=row["content_hash"],
        origin=row["origin"],
        created_at=datetime.fromisoformat(row["created_at"]),
        ontology=from_canonical_json(row["canonical_json"]),
    )
