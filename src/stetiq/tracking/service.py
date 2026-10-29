"""Tracking service: the domain operations the SDK sits on.

`TrackingService` is the interface; `LocalTrackingService` implements it
in-process over a `Store` (local mode). A later remote mode adds a client
implementation of the same interface that talks to the stetiq server, and the
server itself wraps a `LocalTrackingService` over Postgres. The SDK only ever
sees `TrackingService`.

Service methods take and return model/entity values (never YAML text or
store rows); format conversion is the SDK's job.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Protocol

from stetiq.conformance import assess_conformance, candidate_ontology
from stetiq.errors import (
    InvalidEvolutionModeError,
    GraphSourceNotBoundError,
    MissingDeclaredOntologyError,
    NotFoundError,
    RunNotActiveError,
)
from stetiq.graph_source import GraphSourceScope, ObservedSchema
from stetiq.ontology import Ontology, content_hash, from_dict, to_dict
from stetiq.tracking.entities import (
    DEFAULT_EVOLUTION_MODE,
    ConstructionRun,
    EvolutionMode,
    KnowledgeGraph,
    Observation,
    OntologyVersion,
    Origin,
    RunStatus,
)
from stetiq.tracking.store import Store

# What the SDK observed at the end of a run: the scope it read and the Observed Schema.
# The Observation itself happens SDK-side (the Graph Source adapter and its credentials
# live with the user's process, never on the stetiq server).
ObservationInput = tuple[GraphSourceScope, ObservedSchema]


class TrackingService(Protocol):
    def create_knowledge_graph(
        self, name: str, declared_ontology: Ontology | None
    ) -> KnowledgeGraph: ...

    def get_knowledge_graph(self, name: str) -> KnowledgeGraph: ...

    def register_ontology(
        self, knowledge_graph: str, ontology: Ontology, origin: Origin = "registered"
    ) -> OntologyVersion: ...

    def list_ontology_versions(self, knowledge_graph: str) -> list[OntologyVersion]: ...

    def get_ontology_version(self, knowledge_graph: str, number: int) -> OntologyVersion: ...

    def bind_graph_source(self, knowledge_graph: str, scope: GraphSourceScope) -> None: ...

    def get_graph_source(self, knowledge_graph: str) -> GraphSourceScope: ...

    def set_evolution_mode(self, knowledge_graph: str, mode: EvolutionMode) -> None: ...

    def get_evolution_mode(self, knowledge_graph: str) -> EvolutionMode: ...

    def start_run(self, knowledge_graph: str, ontology_version: int) -> ConstructionRun: ...

    def get_run(self, run_id: str) -> ConstructionRun: ...

    def list_runs(self, knowledge_graph: str) -> list[ConstructionRun]: ...

    def log_params(self, run_id: str, params: dict[str, str]) -> None: ...

    def log_metrics(self, run_id: str, metrics: dict[str, float]) -> None: ...

    def end_run(self, run_id: str, observation: ObservationInput) -> ConstructionRun: ...

    def fail_run(self, run_id: str) -> ConstructionRun: ...

    def get_observation(self, observation_id: str) -> Observation: ...

    def list_observations(self, knowledge_graph: str) -> list[Observation]: ...


class LocalTrackingService:
    def __init__(self, store: Store) -> None:
        self._store = store

    def create_knowledge_graph(
        self, name: str, declared_ontology: Ontology | None
    ) -> KnowledgeGraph:
        if declared_ontology is None:
            raise MissingDeclaredOntologyError(
                f"Knowledge Graph {name!r} needs a Declared Ontology"
            )
        kg = KnowledgeGraph(name=name, created_at=_now())
        with self._store.transaction():
            self._store.add_knowledge_graph(kg)
            self._register(name, declared_ontology, "registered")
        return kg

    def get_knowledge_graph(self, name: str) -> KnowledgeGraph:
        kg = self._store.get_knowledge_graph(name)
        if kg is None:
            raise NotFoundError(f"Knowledge Graph {name!r} does not exist")
        return kg

    def register_ontology(
        self, knowledge_graph: str, ontology: Ontology, origin: Origin = "registered"
    ) -> OntologyVersion:
        with self._store.transaction():
            self.get_knowledge_graph(knowledge_graph)
            return self._register(knowledge_graph, ontology, origin)

    def _register(self, knowledge_graph: str, ontology: Ontology, origin: Origin) -> OntologyVersion:
        # Hold the canonical form, so the returned version equals it fetched back.
        ontology = from_dict(to_dict(ontology))
        digest = content_hash(ontology)
        existing = self._store.find_ontology_version_by_hash(knowledge_graph, digest)
        if existing is not None:
            return existing
        versions = self._store.list_ontology_versions(knowledge_graph)
        version = OntologyVersion(
            knowledge_graph=knowledge_graph,
            number=(versions[-1].number + 1) if versions else 1,
            content_hash=digest,
            origin=origin,
            created_at=_now(),
            ontology=ontology,
        )
        self._store.add_ontology_version(version)
        return version

    def list_ontology_versions(self, knowledge_graph: str) -> list[OntologyVersion]:
        self.get_knowledge_graph(knowledge_graph)
        return self._store.list_ontology_versions(knowledge_graph)

    def get_ontology_version(self, knowledge_graph: str, number: int) -> OntologyVersion:
        self.get_knowledge_graph(knowledge_graph)
        version = self._store.get_ontology_version(knowledge_graph, number)
        if version is None:
            raise NotFoundError(
                f"Knowledge Graph {knowledge_graph!r} has no Ontology Version {number}"
            )
        return version

    # --- Graph Source binding -------------------------------------------------------

    def bind_graph_source(self, knowledge_graph: str, scope: GraphSourceScope) -> None:
        with self._store.transaction():
            self.get_knowledge_graph(knowledge_graph)
            self._store.set_graph_source(knowledge_graph, scope)

    def get_graph_source(self, knowledge_graph: str) -> GraphSourceScope:
        self.get_knowledge_graph(knowledge_graph)
        scope = self._store.get_graph_source(knowledge_graph)
        if scope is None:
            raise GraphSourceNotBoundError(
                f"Knowledge Graph {knowledge_graph!r} is not bound to a Graph Source"
            )
        return scope

    # --- Evolution Mode -------------------------------------------------------------

    def set_evolution_mode(self, knowledge_graph: str, mode: EvolutionMode) -> None:
        if mode not in ("strict", "evolving"):
            raise InvalidEvolutionModeError(
                f"Unknown Evolution Mode {mode!r} (expected 'strict' or 'evolving')"
            )
        with self._store.transaction():
            self.get_knowledge_graph(knowledge_graph)
            self._store.set_evolution_mode(knowledge_graph, mode)

    def get_evolution_mode(self, knowledge_graph: str) -> EvolutionMode:
        self.get_knowledge_graph(knowledge_graph)
        return self._store.get_evolution_mode(knowledge_graph) or DEFAULT_EVOLUTION_MODE

    # --- Construction Runs ----------------------------------------------------------

    def start_run(self, knowledge_graph: str, ontology_version: int) -> ConstructionRun:
        with self._store.transaction():
            self.get_ontology_version(knowledge_graph, ontology_version)
            self.get_graph_source(knowledge_graph)  # ending the run will observe it
            run = ConstructionRun(
                id=uuid.uuid4().hex,
                knowledge_graph=knowledge_graph,
                ontology_version=ontology_version,
                status="running",
                started_at=_now(),
            )
            self._store.add_run(run)
        return run

    def get_run(self, run_id: str) -> ConstructionRun:
        run = self._store.get_run(run_id)
        if run is None:
            raise NotFoundError(f"Construction Run {run_id!r} does not exist")
        return run

    def list_runs(self, knowledge_graph: str) -> list[ConstructionRun]:
        self.get_knowledge_graph(knowledge_graph)
        return self._store.list_runs(knowledge_graph)

    def _running(self, run_id: str) -> ConstructionRun:
        run = self.get_run(run_id)
        if run.status != "running":
            raise RunNotActiveError(f"Construction Run {run_id!r} has already {run.status}")
        return run

    def log_params(self, run_id: str, params: dict[str, str]) -> None:
        with self._store.transaction():
            self._running(run_id)
            self._store.set_run_params(run_id, params)

    def log_metrics(self, run_id: str, metrics: dict[str, float]) -> None:
        with self._store.transaction():
            self._running(run_id)
            self._store.set_run_metrics(run_id, metrics)

    def end_run(self, run_id: str, observation: ObservationInput) -> ConstructionRun:
        """Finish the run with the Observation of its Graph Source made at its end."""
        scope, schema = observation
        with self._store.transaction():
            run = self._running(run_id)
            ended = _now()
            obs = Observation(
                id=uuid.uuid4().hex,
                knowledge_graph=run.knowledge_graph,
                scope=scope,
                observed_at=ended,
                schema=schema,
                run_id=run_id,
            )
            self._store.add_observation(obs)
            # Conformance, then Evolution Mode handling: a run introducing new Concepts
            # fails (strict) or gives rise to a Candidate linked to it (evolving).
            declared = self.get_ontology_version(run.knowledge_graph, run.ontology_version)
            conformance = assess_conformance(declared.ontology, schema)
            self._store.set_run_conformance(run_id, conformance)
            status: RunStatus = "finished"
            candidate = candidate_ontology(declared.ontology, schema)
            if candidate is not None:
                if self.get_evolution_mode(run.knowledge_graph) == "strict":
                    status = "failed"
                else:
                    version = self._register(run.knowledge_graph, candidate, "run")
                    self._store.set_run_candidate(run_id, run.knowledge_graph, version.number)
            self._store.end_run(run_id, status, ended, obs.id)
            return self.get_run(run_id)

    def fail_run(self, run_id: str) -> ConstructionRun:
        with self._store.transaction():
            self._running(run_id)
            self._store.end_run(run_id, "failed", _now(), None)
            return self.get_run(run_id)

    def get_observation(self, observation_id: str) -> Observation:
        obs = self._store.get_observation(observation_id)
        if obs is None:
            raise NotFoundError(f"Observation {observation_id!r} does not exist")
        return obs

    def list_observations(self, knowledge_graph: str) -> list[Observation]:
        self.get_knowledge_graph(knowledge_graph)
        return self._store.list_observations(knowledge_graph)


def _now() -> datetime:
    return datetime.now(UTC)
