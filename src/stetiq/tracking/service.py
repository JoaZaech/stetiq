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

import json
import uuid
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Protocol

from stetiq.errors import (
    EvaluatorError,
    GraphSourceNotBoundError,
    MissingDeclaredOntologyError,
    NotFoundError,
    RunNotActiveError,
)
from stetiq.evaluation.framework import (
    Evaluation,
    ParameterValue,
    SubjectKind,
    check_evaluation,
    check_parameters,
)
from stetiq.evaluation.structural import BUILT_IN_EVALUATORS
from stetiq.graph_source import GraphSourceScope, ObservedSchema
from stetiq.ontology import Ontology, content_hash
from stetiq.tracking.entities import (
    DEFAULT_CONTRACT_ALIAS,
    Alias,
    Promotion,
    validate_alias_name,
    ConstructionRun,
    EvaluationResult,
    KnowledgeGraph,
    Observation,
    OntologyVersion,
    Origin,
)
from stetiq.tracking.store import Store

# What the SDK observed at the end of a run: the scope it read and the Observed Schema.
# The Observation itself happens SDK-side (the Graph Source adapter and its credentials
# live with the user's process, never on the stetiq server).
ObservationInput = tuple[GraphSourceScope, ObservedSchema]

# The audit-log actor for Alias moves stetiq makes itself (the Contract Alias on creation).
SYSTEM_ACTOR = "stetiq"


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

    def start_run(self, knowledge_graph: str, ontology_version: int) -> ConstructionRun: ...

    def get_run(self, run_id: str) -> ConstructionRun: ...

    def list_runs(self, knowledge_graph: str) -> list[ConstructionRun]: ...

    def log_params(self, run_id: str, params: dict[str, str]) -> None: ...

    def log_metrics(self, run_id: str, metrics: dict[str, float]) -> None: ...

    def end_run(self, run_id: str, observation: ObservationInput) -> ConstructionRun: ...

    def fail_run(self, run_id: str) -> ConstructionRun: ...

    def get_observation(self, observation_id: str) -> Observation: ...

    def list_observations(self, knowledge_graph: str) -> list[Observation]: ...

    def set_alias(
        self, knowledge_graph: str, name: str, version: int, actor: str
    ) -> Alias: ...

    def get_alias(self, knowledge_graph: str, name: str) -> Alias: ...

    def list_aliases(self, knowledge_graph: str) -> list[Alias]: ...

    def list_promotions(self, knowledge_graph: str) -> list[Promotion]: ...

    def set_contract_alias(self, knowledge_graph: str, alias: str) -> None: ...

    def get_contract_alias(self, knowledge_graph: str) -> str: ...

    def evaluate_ontology_version(
        self, knowledge_graph: str, number: int
    ) -> list[EvaluationResult]:
        """(Re-)run the built-in Evaluators on an Ontology Version and store the results."""
        ...

    def record_evaluation(
        self,
        knowledge_graph: str,
        subject_kind: SubjectKind,
        subject_id: str,
        evaluator: str,
        evaluation: Evaluation,
        parameters: Mapping[str, ParameterValue] | None = None,
    ) -> EvaluationResult:
        """Store a result computed elsewhere (a custom Evaluator run by the SDK).

        `parameters` is the Evaluator's configuration; results are kept per
        (evaluator, parameters)."""
        ...

    def get_evaluation_results(
        self, knowledge_graph: str, subject_kind: SubjectKind, subject_id: str
    ) -> list[EvaluationResult]:
        """The latest result per (Evaluator, parameters) for the subject, ordered by
        Evaluator name then parameters."""
        ...


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
            v1 = self._register(name, declared_ontology, "registered")
            # The initial Declared Ontology is the contract until something is promoted.
            self._move_alias(name, DEFAULT_CONTRACT_ALIAS, v1.number, SYSTEM_ACTOR)
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
        self._run_built_ins(version)
        return version

    def _run_built_ins(self, version: OntologyVersion) -> list[EvaluationResult]:
        return [
            self._store_result(
                version.knowledge_graph,
                "ontology_version",
                str(version.number),
                evaluator.name,
                check_evaluation(evaluator.name, evaluator.evaluate(version)),
            )
            for evaluator in BUILT_IN_EVALUATORS
        ]

    def _store_result(
        self,
        knowledge_graph: str,
        subject_kind: SubjectKind,
        subject_id: str,
        evaluator: str,
        evaluation: Evaluation,
        parameters: Mapping[str, ParameterValue] | None = None,
    ) -> EvaluationResult:
        result = EvaluationResult(
            knowledge_graph=knowledge_graph,
            subject_kind=subject_kind,
            subject_id=subject_id,
            evaluator=evaluator,
            metrics=dict(evaluation.metrics),
            details=tuple(evaluation.details),
            created_at=_now(),
            parameters=dict(parameters or {}),
        )
        self._store.add_evaluation_result(result)
        return result

    def _check_subject(
        self, knowledge_graph: str, subject_kind: SubjectKind, subject_id: str
    ) -> None:
        if subject_kind == "ontology_version":
            if not subject_id.isdigit():
                raise NotFoundError(
                    f"Knowledge Graph {knowledge_graph!r} has no Ontology Version {subject_id!r}"
                )
            self.get_ontology_version(knowledge_graph, int(subject_id))
        else:
            # Construction Run subjects arrive with run-level evaluation (ticket #13).
            raise EvaluatorError(f"Unsupported evaluation subject kind {subject_kind!r}")

    def evaluate_ontology_version(
        self, knowledge_graph: str, number: int
    ) -> list[EvaluationResult]:
        with self._store.transaction():
            return self._run_built_ins(self.get_ontology_version(knowledge_graph, number))

    def record_evaluation(
        self,
        knowledge_graph: str,
        subject_kind: SubjectKind,
        subject_id: str,
        evaluator: str,
        evaluation: Evaluation,
        parameters: Mapping[str, ParameterValue] | None = None,
    ) -> EvaluationResult:
        if evaluator in {e.name for e in BUILT_IN_EVALUATORS}:
            raise EvaluatorError(f"{evaluator!r} is a built-in Evaluator; its results are computed by stetiq")
        evaluation = check_evaluation(evaluator, evaluation)
        parameters = check_parameters(evaluator, parameters or {})
        with self._store.transaction():
            self._check_subject(knowledge_graph, subject_kind, subject_id)
            return self._store_result(
                knowledge_graph, subject_kind, subject_id, evaluator, evaluation, parameters
            )

    def get_evaluation_results(
        self, knowledge_graph: str, subject_kind: SubjectKind, subject_id: str
    ) -> list[EvaluationResult]:
        self._check_subject(knowledge_graph, subject_kind, subject_id)
        latest = {
            (r.evaluator, json.dumps(r.parameters, sort_keys=True)): r
            for r in self._store.list_evaluation_results(knowledge_graph, subject_kind, subject_id)
        }
        return [latest[key] for key in sorted(latest)]

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
            self._store.end_run(run_id, "finished", ended, obs.id)
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

    # --- Aliases and Promotion ------------------------------------------------------

    def set_alias(self, knowledge_graph: str, name: str, version: int, actor: str) -> Alias:
        """Create the Alias or move it (a Promotion); every move is audit-logged.

        Pointing an Alias at the version it already points to changes nothing and
        logs nothing. Promotion is never blocked: Gates only show up in the log."""
        validate_alias_name(name)
        with self._store.transaction():
            self.get_ontology_version(knowledge_graph, version)
            return self._move_alias(knowledge_graph, name, version, actor)

    def _move_alias(self, knowledge_graph: str, name: str, version: int, actor: str) -> Alias:
        with self._store.transaction():
            current = self._store.get_alias(knowledge_graph, name)
            if current is not None and current.version == version:
                return current
            moved = _now()
            alias = Alias(knowledge_graph=knowledge_graph, name=name, version=version, updated_at=moved)
            self._store.set_alias(alias)
            self._store.add_promotion(
                Promotion(
                    knowledge_graph=knowledge_graph,
                    alias=name,
                    from_version=None if current is None else current.version,
                    to_version=version,
                    actor=actor,
                    promoted_at=moved,
                    gate_result=None,  # Gates (#14) fill in the target's latest result
                )
            )
            return alias

    def get_alias(self, knowledge_graph: str, name: str) -> Alias:
        self.get_knowledge_graph(knowledge_graph)
        alias = self._store.get_alias(knowledge_graph, name)
        if alias is None:
            raise NotFoundError(f"Knowledge Graph {knowledge_graph!r} has no Alias {name!r}")
        return alias

    def list_aliases(self, knowledge_graph: str) -> list[Alias]:
        self.get_knowledge_graph(knowledge_graph)
        return self._store.list_aliases(knowledge_graph)

    def list_promotions(self, knowledge_graph: str) -> list[Promotion]:
        self.get_knowledge_graph(knowledge_graph)
        return self._store.list_promotions(knowledge_graph)

    def set_contract_alias(self, knowledge_graph: str, alias: str) -> None:
        with self._store.transaction():
            self.get_alias(knowledge_graph, alias)
            self._store.set_contract_alias(knowledge_graph, alias)

    def get_contract_alias(self, knowledge_graph: str) -> str:
        self.get_knowledge_graph(knowledge_graph)
        return self._store.get_contract_alias(knowledge_graph) or DEFAULT_CONTRACT_ALIAS


def _now() -> datetime:
    return datetime.now(UTC)
