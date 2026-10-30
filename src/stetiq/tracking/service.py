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

from stetiq.conformance import assess_conformance, candidate_ontology
from stetiq.drift import DriftThresholds, assess_drift
from stetiq.errors import (
    EvaluatorError,
    GraphSourceNotBoundError,
    InvalidEvolutionModeError,
    MissingDeclaredOntologyError,
    NotFoundError,
    RunNotActiveError,
)
from stetiq.evaluation.answerability import (
    ANSWERABILITY_EVALUATOR,
    CompetencyQuestionMapper,
    StructuralAnswerability,
)
from stetiq.evaluation.framework import (
    Evaluation,
    ParameterValue,
    SubjectKind,
    check_evaluation,
    check_parameters,
)
from stetiq.evaluation.structural import BUILT_IN_EVALUATORS
from stetiq.evaluation.run import (
    CQ_EXECUTION_EVALUATOR,
    SERVER_RUN_EVALUATORS,
    NoGraphSource,
    RunSubject,
)
from stetiq.gates import GateOutcome
from stetiq.graph_source import GraphSourceScope, ObservedSchema
from stetiq.ontology import Ontology, content_hash, from_dict, to_dict
from stetiq.tracking.entities import (
    DEFAULT_CONTRACT_ALIAS,
    DEFAULT_EVOLUTION_MODE,
    Alias,
    ConstructionRun,
    DriftEvent,
    EvaluationResult,
    EvolutionMode,
    GateResult,
    GateSubjectKind,
    KnowledgeGraph,
    Observation,
    ObservationOutcome,
    OntologyVersion,
    Origin,
    UseCaseVersion,
    Promotion,
    RunStatus,
    validate_alias_name,
)
from stetiq.tracking.store import Store
from stetiq import use_case as use_case_format
from stetiq.use_case import UseCase

# What the SDK observed at the end of a run: the scope it read and the Observed Schema.
# The Observation itself happens SDK-side (the Graph Source adapter and its credentials
# live with the user's process, never on the stetiq server).
ObservationInput = tuple[GraphSourceScope, ObservedSchema]

# Evaluator names stetiq computes itself; custom Evaluators cannot take them.
RESERVED_EVALUATOR_NAMES = frozenset(
    {e.name for e in BUILT_IN_EVALUATORS}
    | {ANSWERABILITY_EVALUATOR, CQ_EXECUTION_EVALUATOR}
    | {e.name for e in SERVER_RUN_EVALUATORS}
)

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

    def record_observation(
        self,
        knowledge_graph: str,
        observation: ObservationInput,
        thresholds: DriftThresholds | None = None,
    ) -> ObservationOutcome:
        """Store an on-demand Observation (no run) and check it for Drift against the
        Contract Alias's version and the previous Observation. Never creates a version."""
        ...

    def list_drift_events(self, knowledge_graph: str) -> list[DriftEvent]: ...

    def set_alias(
        self, knowledge_graph: str, name: str, version: int, actor: str
    ) -> Alias: ...

    def get_alias(self, knowledge_graph: str, name: str) -> Alias: ...

    def list_aliases(self, knowledge_graph: str) -> list[Alias]: ...

    def list_promotions(self, knowledge_graph: str) -> list[Promotion]: ...

    def set_contract_alias(self, knowledge_graph: str, alias: str) -> None: ...

    def get_contract_alias(self, knowledge_graph: str) -> str: ...

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
        parameters: Mapping[str, ParameterValue] | None = None,
        *,
        use_case_version: int | None = None,
    ) -> EvaluationResult:
        """Store a result computed elsewhere (a custom Evaluator run by the SDK, or
        `competency_question_execution`, which needs the SDK's Graph Source).

        `parameters` is the Evaluator's configuration; results are kept per
        (evaluator, parameters). `use_case_version` is the Use Case version the
        result was judged against (must exist), or None."""
        ...

    def get_evaluation_results(
        self, knowledge_graph: str, subject_kind: SubjectKind, subject_id: str
    ) -> list[EvaluationResult]:
        """The latest result per (Evaluator, parameters) for the subject, ordered by
        Evaluator name then parameters."""
        ...

    def evaluate_construction_run(self, run_id: str) -> list[EvaluationResult]:
        """(Re-)run the built-in run Evaluators that need no Graph Source access
        (`conformance`, `observed_schema`) on a run with an Observation, and store the
        results. Raises EvaluatorError for a run that has no Observation."""
        ...

    def register_use_case(self, knowledge_graph: str, use_case: UseCase) -> UseCaseVersion:
        """Store a new Use Case version (identical content returns the existing one).
        Never creates an Ontology Version."""
        ...

    def list_use_case_versions(self, knowledge_graph: str) -> list[UseCaseVersion]: ...

    def get_use_case_version(self, knowledge_graph: str, number: int) -> UseCaseVersion: ...

    def record_gate_result(
        self,
        knowledge_graph: str,
        subject_kind: GateSubjectKind,
        subject_id: str,
        outcomes: tuple[GateOutcome, ...],
    ) -> GateResult:
        """Record a Gate evaluation (computed by the SDK from the repo's Gates) together
        with the Gate definitions it used. The service resolves which Ontology Version
        the subject stands for."""
        ...

    def list_gate_results(self, knowledge_graph: str) -> list[GateResult]:
        """Every recorded Gate evaluation, oldest first."""
        ...


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
        parameters: Mapping[str, ParameterValue] | None = None,
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
            parameters=dict(parameters or {}),
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
        elif subject_kind == "construction_run":
            run = self._store.get_run(subject_id)
            if run is None or run.knowledge_graph != knowledge_graph:
                raise NotFoundError(
                    f"Knowledge Graph {knowledge_graph!r} has no Construction Run {subject_id!r}"
                )
        else:
            raise EvaluatorError(f"Unsupported evaluation subject kind {subject_kind!r}")

    def _run_subject(self, run: ConstructionRun) -> RunSubject:
        if run.observation_id is None:
            raise EvaluatorError(
                f"Construction Run {run.id!r} has no Observation to evaluate "
                f"(it is {run.status} without having ended)"
            )
        return RunSubject(
            run=run,
            declared_ontology=self.get_ontology_version(run.knowledge_graph, run.ontology_version),
            observation=self.get_observation(run.observation_id),
            graph_source=NoGraphSource(),
        )

    def _run_run_built_ins(self, run: ConstructionRun) -> list[EvaluationResult]:
        subject = self._run_subject(run)
        return [
            self._store_result(
                run.knowledge_graph,
                "construction_run",
                run.id,
                evaluator.name,
                check_evaluation(evaluator.name, evaluator.evaluate(subject)),
            )
            for evaluator in SERVER_RUN_EVALUATORS
        ]

    def evaluate_construction_run(self, run_id: str) -> list[EvaluationResult]:
        with self._store.transaction():
            return self._run_run_built_ins(self.get_run(run_id))

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
        parameters: Mapping[str, ParameterValue] | None = None,
        *,
        use_case_version: int | None = None,
    ) -> EvaluationResult:
        # Executed Competency Questions are a built-in computed SDK-side (the Graph
        # Source lives there), so only that name is accepted, and only on a run.
        sdk_side = subject_kind == "construction_run" and evaluator == CQ_EXECUTION_EVALUATOR
        if evaluator in RESERVED_EVALUATOR_NAMES and not sdk_side:
            raise EvaluatorError(f"{evaluator!r} is a built-in Evaluator; its results are computed by stetiq")
        evaluation = check_evaluation(evaluator, evaluation)
        parameters = check_parameters(evaluator, parameters or {})
        with self._store.transaction():
            self._check_subject(knowledge_graph, subject_kind, subject_id)
            if use_case_version is not None:
                self.get_use_case_version(knowledge_graph, use_case_version)
            return self._store_result(
                knowledge_graph,
                subject_kind,
                subject_id,
                evaluator,
                evaluation,
                parameters,
                use_case_version=use_case_version,
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
            run = self.get_run(run_id)
            self._run_run_built_ins(run)
            return run

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

    # --- On-demand Observation and Drift --------------------------------------------

    def record_observation(
        self,
        knowledge_graph: str,
        observation: ObservationInput,
        thresholds: DriftThresholds | None = None,
    ) -> ObservationOutcome:
        scope, schema = observation
        thresholds = thresholds or DriftThresholds()
        with self._store.transaction():
            self.get_knowledge_graph(knowledge_graph)
            history = self._store.list_observations(knowledge_graph)
            previous = history[-1] if history else None
            obs = Observation(
                id=uuid.uuid4().hex,
                knowledge_graph=knowledge_graph,
                scope=scope,
                observed_at=_now(),
                schema=schema,
                run_id=None,
            )
            self._store.add_observation(obs)
            contract_alias = self.get_contract_alias(knowledge_graph)
            contract = self.get_ontology_version(
                knowledge_graph, self.get_alias(knowledge_graph, contract_alias).version
            )
            findings = assess_drift(
                contract.ontology, schema, None if previous is None else previous.schema, thresholds
            )
            if not findings:
                return ObservationOutcome(observation=obs)
            event = DriftEvent(
                id=uuid.uuid4().hex,
                knowledge_graph=knowledge_graph,
                observation_id=obs.id,
                previous_observation_id=None if previous is None else previous.id,
                contract_alias=contract_alias,
                ontology_version=contract.number,
                detected_at=obs.observed_at,
                findings=findings,
                thresholds=thresholds,
            )
            self._store.add_drift_event(event)
            return ObservationOutcome(observation=obs, drift=event)

    def list_drift_events(self, knowledge_graph: str) -> list[DriftEvent]:
        self.get_knowledge_graph(knowledge_graph)
        return self._store.list_drift_events(knowledge_graph)

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
                    gate_result=self._latest_gate_verdict(knowledge_graph, version),
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

    # --- Gates ----------------------------------------------------------------------

    def record_gate_result(
        self,
        knowledge_graph: str,
        subject_kind: GateSubjectKind,
        subject_id: str,
        outcomes: tuple[GateOutcome, ...],
    ) -> GateResult:
        with self._store.transaction():
            result = GateResult(
                knowledge_graph=knowledge_graph,
                subject_kind=subject_kind,
                subject_id=subject_id,
                ontology_version=self._gate_subject_version(knowledge_graph, subject_kind, subject_id),
                outcomes=tuple(outcomes),
                evaluated_at=_now(),
            )
            self._store.add_gate_result(result)
            return result

    def list_gate_results(self, knowledge_graph: str) -> list[GateResult]:
        self.get_knowledge_graph(knowledge_graph)
        return self._store.list_gate_results(knowledge_graph)

    def _gate_subject_version(
        self, knowledge_graph: str, subject_kind: GateSubjectKind, subject_id: str
    ) -> int:
        """The Ontology Version a Gate subject stands for: the version itself; for a run
        the Candidate it gave rise to, else the version it consumed."""
        if subject_kind == "ontology_version":
            if not subject_id.isdigit():
                raise NotFoundError(
                    f"Knowledge Graph {knowledge_graph!r} has no Ontology Version {subject_id!r}"
                )
            return self.get_ontology_version(knowledge_graph, int(subject_id)).number
        if subject_kind == "construction_run":
            run = self.get_run(subject_id)
            if run.knowledge_graph != knowledge_graph:
                raise NotFoundError(
                    f"Knowledge Graph {knowledge_graph!r} has no Construction Run {subject_id!r}"
                )
            return run.candidate_version or run.ontology_version
        raise NotFoundError(f"Unknown Gate subject kind {subject_kind!r}")

    def _latest_gate_verdict(self, knowledge_graph: str, version: int) -> str | None:
        """"passed"/"failed" for the version's latest Gate result; None if never gated."""
        for result in reversed(self._store.list_gate_results(knowledge_graph)):
            if result.ontology_version == version:
                return "passed" if result.passed else "failed"
        return None


def _now() -> datetime:
    return datetime.now(UTC)
