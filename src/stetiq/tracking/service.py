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

from stetiq.errors import (
    EvaluatorError,
    GraphSourceNotBoundError,
    MissingDeclaredOntologyError,
    NotFoundError,
    RunNotActiveError,
)
from stetiq.evaluation.framework import Evaluation, SubjectKind, check_evaluation
from stetiq.evaluation.answerability import (
    ANSWERABILITY_EVALUATOR,
    CompetencyQuestionMapper,
    StructuralAnswerability,
)
from stetiq.evaluation.structural import BUILT_IN_EVALUATORS
from stetiq.graph_source import GraphSourceScope, ObservedSchema
from stetiq.ontology import Ontology, content_hash
from stetiq.tracking.entities import (
    ConstructionRun,
    EvaluationResult,
    KnowledgeGraph,
    Observation,
    OntologyVersion,
    Origin,
    UseCaseVersion,
)
from stetiq.tracking.store import Store
from stetiq import use_case as use_case_format
from stetiq.use_case import UseCase

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

    def start_run(self, knowledge_graph: str, ontology_version: int) -> ConstructionRun: ...

    def get_run(self, run_id: str) -> ConstructionRun: ...

    def list_runs(self, knowledge_graph: str) -> list[ConstructionRun]: ...

    def log_params(self, run_id: str, params: dict[str, str]) -> None: ...

    def log_metrics(self, run_id: str, metrics: dict[str, float]) -> None: ...

    def end_run(self, run_id: str, observation: ObservationInput) -> ConstructionRun: ...

    def fail_run(self, run_id: str) -> ConstructionRun: ...

    def get_observation(self, observation_id: str) -> Observation: ...

    def list_observations(self, knowledge_graph: str) -> list[Observation]: ...

    def evaluate_ontology_version(
        self, knowledge_graph: str, number: int, use_case_version: int | None = None
    ) -> list[EvaluationResult]:
        """(Re-)run the built-in Evaluators on an Ontology Version and store the results.

        Structural answerability is judged against `use_case_version` (default: the
        latest Use Case version; skipped when the Knowledge Graph has no Use Case)."""
        ...

    def record_evaluation(
        self,
        knowledge_graph: str,
        subject_kind: SubjectKind,
        subject_id: str,
        evaluator: str,
        evaluation: Evaluation,
    ) -> EvaluationResult:
        """Store a result computed elsewhere (a custom Evaluator run by the SDK)."""
        ...

    def get_evaluation_results(
        self, knowledge_graph: str, subject_kind: SubjectKind, subject_id: str
    ) -> list[EvaluationResult]:
        """The latest result per Evaluator for the subject, ordered by Evaluator name."""
        ...

    def register_use_case(self, knowledge_graph: str, use_case: UseCase) -> UseCaseVersion:
        """Store a new Use Case version (identical content returns the existing one).
        Never creates an Ontology Version."""
        ...

    def list_use_case_versions(self, knowledge_graph: str) -> list[UseCaseVersion]: ...

    def get_use_case_version(self, knowledge_graph: str, number: int) -> UseCaseVersion: ...


class LocalTrackingService:
    def __init__(
        self, store: Store, *, question_mapper: CompetencyQuestionMapper | None = None
    ) -> None:
        """`question_mapper` is the model interface structural answerability uses for
        Competency Questions with neither a Concept mapping nor a query (ticket #12)."""
        self._store = store
        self._question_mapper = question_mapper

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
        self._run_answerability(version)
        return version

    def _run_answerability(
        self, version: OntologyVersion, use_case_version: int | None = None
    ) -> list[EvaluationResult]:
        """Structural answerability against a Use Case version (default: the latest)."""
        if use_case_version is None:
            versions = self._store.list_use_case_versions(version.knowledge_graph)
            if not versions:
                return []
            use_case = versions[-1]
        else:
            use_case = self.get_use_case_version(version.knowledge_graph, use_case_version)
        evaluator = StructuralAnswerability(use_case.use_case, self._question_mapper)
        return [
            self._store_result(
                version.knowledge_graph,
                "ontology_version",
                str(version.number),
                evaluator.name,
                check_evaluation(evaluator.name, evaluator.evaluate(version)),
                use_case_version=use_case.number,
            )
        ]

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
        *,
        use_case_version: int | None = None,
    ) -> EvaluationResult:
        result = EvaluationResult(
            knowledge_graph=knowledge_graph,
            subject_kind=subject_kind,
            subject_id=subject_id,
            evaluator=evaluator,
            metrics=dict(evaluation.metrics),
            details=tuple(evaluation.details),
            created_at=_now(),
            use_case_version=use_case_version,
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
        self, knowledge_graph: str, number: int, use_case_version: int | None = None
    ) -> list[EvaluationResult]:
        with self._store.transaction():
            version = self.get_ontology_version(knowledge_graph, number)
            return self._run_built_ins(version) + self._run_answerability(
                version, use_case_version
            )

    def record_evaluation(
        self,
        knowledge_graph: str,
        subject_kind: SubjectKind,
        subject_id: str,
        evaluator: str,
        evaluation: Evaluation,
    ) -> EvaluationResult:
        if evaluator in {e.name for e in BUILT_IN_EVALUATORS} | {ANSWERABILITY_EVALUATOR}:
            raise EvaluatorError(f"{evaluator!r} is a built-in Evaluator; its results are computed by stetiq")
        evaluation = check_evaluation(evaluator, evaluation)
        with self._store.transaction():
            self._check_subject(knowledge_graph, subject_kind, subject_id)
            return self._store_result(
                knowledge_graph, subject_kind, subject_id, evaluator, evaluation
            )

    def get_evaluation_results(
        self, knowledge_graph: str, subject_kind: SubjectKind, subject_id: str
    ) -> list[EvaluationResult]:
        self._check_subject(knowledge_graph, subject_kind, subject_id)
        latest = {
            r.evaluator: r
            for r in self._store.list_evaluation_results(knowledge_graph, subject_kind, subject_id)
        }
        return [latest[name] for name in sorted(latest)]

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

    # --- Use Cases ------------------------------------------------------------------

    def register_use_case(self, knowledge_graph: str, use_case: UseCase) -> UseCaseVersion:
        use_case = use_case_format.canonicalize(use_case_format.check_use_case(use_case))
        digest = use_case_format.content_hash(use_case)
        with self._store.transaction():
            self.get_knowledge_graph(knowledge_graph)
            existing = self._store.find_use_case_version_by_hash(knowledge_graph, digest)
            if existing is not None:
                return existing
            versions = self._store.list_use_case_versions(knowledge_graph)
            version = UseCaseVersion(
                knowledge_graph=knowledge_graph,
                number=(versions[-1].number + 1) if versions else 1,
                content_hash=digest,
                created_at=_now(),
                use_case=use_case,
            )
            self._store.add_use_case_version(version)
            return version

    def list_use_case_versions(self, knowledge_graph: str) -> list[UseCaseVersion]:
        self.get_knowledge_graph(knowledge_graph)
        return self._store.list_use_case_versions(knowledge_graph)

    def get_use_case_version(self, knowledge_graph: str, number: int) -> UseCaseVersion:
        self.get_knowledge_graph(knowledge_graph)
        version = self._store.get_use_case_version(knowledge_graph, number)
        if version is None:
            raise NotFoundError(
                f"Knowledge Graph {knowledge_graph!r} has no Use Case version {number}"
            )
        return version


def _now() -> datetime:
    return datetime.now(UTC)
