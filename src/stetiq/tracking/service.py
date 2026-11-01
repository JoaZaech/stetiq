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
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Protocol, get_args

from stetiq import use_case as use_case_format
from stetiq.conformance import apply_definitions, assess_conformance, candidate_ontology
from stetiq.drift import DriftThresholds, assess_drift
from stetiq.errors import (
    ConflictingArgumentsError,
    EvaluatorError,
    GateConfigError,
    GraphSourceNotBoundError,
    InvalidEvolutionModeError,
    MissingDeclaredOntologyError,
    NoConsumerGatesError,
    NotFoundError,
    NoUseCaseError,
    OntologyValidationError,
    RunNotActiveError,
    RunNotFinishedError,
)
from stetiq.evaluation.answerability import (
    ANSWERABILITY_EVALUATOR,
    COVERAGE_EVALUATOR,
    UNJUSTIFIED_ADDITIONS_EVALUATOR,
    CompetencyQuestionCoverage,
    CompetencyQuestionMapper,
    StructuralAnswerability,
    UnjustifiedAdditions,
)
from stetiq.evaluation.framework import (
    Evaluation,
    OntologyVersionEvaluator,
    ParameterValue,
    SubjectKind,
    check_evaluation,
    check_parameters,
)
from stetiq.evaluation.run import (
    CQ_EXECUTION_EVALUATOR,
    SERVER_RUN_EVALUATORS,
    NoGraphSource,
    RunSubject,
    executed_questions,
)
from stetiq.evaluation.structural import BUILT_IN_EVALUATORS
from stetiq.gates import Gate, GateInputs
from stetiq.gates import evaluate_gates as run_gates
from stetiq.graph_source import GraphSourceScope, ObservedSchema
from stetiq.ontology import Ontology, content_hash, from_dict, to_dict
from stetiq.ontology.diff import diff_ontologies
from stetiq.tracking.entities import (
    DEFAULT_CONTRACT_ALIAS,
    DEFAULT_EVOLUTION_MODE,
    Alias,
    ConstructionRun,
    ConsumerGateResult,
    DriftEvent,
    EvaluationResult,
    EvolutionMode,
    GatePreview,
    GatePreviewSource,
    GateResult,
    KnowledgeGraph,
    KnowledgeGraphSummary,
    Observation,
    ObservationOutcome,
    OntologyVersion,
    Origin,
    Promotion,
    RunStatus,
    UseCaseVersion,
    validate_alias_name,
)
from stetiq.tracking.store import Store
from stetiq.use_case import UseCase
from stetiq.use_case.concepts import ConceptRef, PropertyRef, parse_concept_reference
from stetiq.use_case.consumer_gates import ConsumerGateInputs, QuestionRows, evaluate_consumer_gate

# What the SDK observed at the end of a run: the scope it read and the Observed Schema.
# The Observation itself happens SDK-side (the Graph Source adapter and its credentials
# live with the user's process, never on the stetiq server).
ObservationInput = tuple[GraphSourceScope, ObservedSchema]

# Evaluator names stetiq computes itself; custom Evaluators cannot take them.
RESERVED_EVALUATOR_NAMES = frozenset(
    {e.name for e in BUILT_IN_EVALUATORS}
    | {
        ANSWERABILITY_EVALUATOR,
        COVERAGE_EVALUATOR,
        UNJUSTIFIED_ADDITIONS_EVALUATOR,
        CQ_EXECUTION_EVALUATOR,
    }
    | {e.name for e in SERVER_RUN_EVALUATORS}
)


def check_not_built_in(evaluator: str) -> None:
    """Refuse a custom Evaluator (or a result recorded for one) that takes a built-in's name.

    The tracking service applies it to recorded results; the SDK also applies it before
    running a custom Evaluator, since those run in the user's process."""
    if evaluator in RESERVED_EVALUATOR_NAMES:
        raise EvaluatorError(
            f"{evaluator!r} is a built-in Evaluator; its results are computed by stetiq"
        )


def check_proposed_definitions(proposals: Mapping[str, str]) -> dict[str, str]:
    """Proposed Definitions, checked: each key a Class, Relation or Attribute reference
    (`Label`, `Owner.name`), each value a non-empty string. The service applies it to the
    end call; the SDK also applies it in `propose_definitions`, so the message is the same
    in every mode."""
    if not isinstance(proposals, Mapping):
        raise OntologyValidationError("proposed Definitions must map Concepts to Definitions")
    checked = {}
    for ref, text in proposals.items():
        try:
            parsed = parse_concept_reference(ref) if isinstance(ref, str) else None
        except ValueError:
            parsed = None
        if not isinstance(parsed, ConceptRef | PropertyRef):
            raise OntologyValidationError(
                f"{ref!r} is not a Concept reference (expected Label or Owner.attribute)"
            )
        if not isinstance(text, str) or not text.strip():
            raise OntologyValidationError(
                f"the proposed Definition of {ref!r} must be a non-empty string"
            )
        checked[ref.strip()] = text
    return checked


# The audit-log actor for Alias moves stetiq makes itself (the Contract Alias on creation).
SYSTEM_ACTOR = "stetiq"


class TrackingService(Protocol):
    def create_knowledge_graph(
        self, name: str, declared_ontology: Ontology | None
    ) -> KnowledgeGraph: ...

    def get_knowledge_graph(self, name: str) -> KnowledgeGraph: ...

    def set_knowledge_graph_description(self, name: str, description: str | None) -> KnowledgeGraph:
        """Replace the markdown description; a blank one clears it."""
        ...

    def list_knowledge_graphs(self) -> list[KnowledgeGraphSummary]:
        """By name, each with a summary of its state. In server mode, only those the API
        token can read."""
        ...

    def register_ontology(self, knowledge_graph: str, ontology: Ontology) -> OntologyVersion:
        """Register a version by hand (origin "registered"; "run" versions only arise
        from ending a Construction Run)."""
        ...

    def list_ontology_versions(self, knowledge_graph: str) -> list[OntologyVersion]: ...

    def get_ontology_version(self, knowledge_graph: str, number: int) -> OntologyVersion: ...

    def list_candidates(self, knowledge_graph: str) -> list[int]:
        """The numbers of the Knowledge Graph's Candidates (Ontology Versions no Alias
        has pointed to yet), ascending."""
        ...

    def bind_graph_source(self, knowledge_graph: str, scope: GraphSourceScope) -> None: ...

    def get_graph_source(self, knowledge_graph: str) -> GraphSourceScope: ...

    def set_evolution_mode(self, knowledge_graph: str, mode: EvolutionMode) -> None: ...

    def get_evolution_mode(self, knowledge_graph: str) -> EvolutionMode: ...

    def start_run(
        self,
        knowledge_graph: str,
        ontology_version: int | None = None,
        *,
        alias: str | None = None,
    ) -> ConstructionRun:
        """Its Declared Ontology is `ontology_version`, or the version `alias` points
        to, or by default the Contract Alias's version."""
        ...

    def get_run(self, run_id: str) -> ConstructionRun: ...

    def list_runs(self, knowledge_graph: str) -> list[ConstructionRun]: ...

    def latest_finished_run(self, knowledge_graph: str, version: int) -> ConstructionRun | None:
        """The latest finished run standing for Ontology Version `version` (its Candidate,
        else the version it consumed); None when no finished run does."""
        ...

    def log_params(self, run_id: str, params: dict[str, str]) -> None: ...

    def log_metrics(self, run_id: str, metrics: dict[str, float]) -> None: ...

    def end_run(
        self,
        run_id: str,
        observation: ObservationInput,
        definitions: Mapping[str, str] | None = None,
    ) -> ConstructionRun:
        """Finish the run with its ending Observation. `definitions` are the run's
        proposed Definitions (Concept reference -> text), applied only to Concepts its
        Candidate adds; the others are listed in `ignored_definitions`."""
        ...

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

    def set_alias(self, knowledge_graph: str, name: str, version: int, actor: str) -> Alias: ...

    def get_alias(self, knowledge_graph: str, name: str) -> Alias: ...

    def list_aliases(self, knowledge_graph: str) -> list[Alias]: ...

    def list_promotions(self, knowledge_graph: str) -> list[Promotion]: ...

    def set_contract_alias(self, knowledge_graph: str, alias: str) -> None: ...

    def get_contract_alias(self, knowledge_graph: str) -> str: ...

    def get_contract_version(self, knowledge_graph: str) -> OntologyVersion:
        """The Ontology Version the Contract Alias points to."""
        ...

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

    def list_evaluation_results(
        self, knowledge_graph: str, subject_kind: SubjectKind
    ) -> list[EvaluationResult]:
        """The latest result per (subject, Evaluator, parameters) across every subject
        of `subject_kind` in the Knowledge Graph: `get_evaluation_results` for each of
        them at once. Subjects come in the order of their first stored result."""
        ...

    def evaluate_construction_run(self, run_id: str) -> list[EvaluationResult]:
        """(Re-)run the built-in run Evaluators that need no Graph Source access
        (`conformance`, `observed_schema`) on a run with an Observation, and store the
        results. Raises EvaluatorError for a run that has no Observation."""
        ...

    def register_use_case(self, knowledge_graph: str, use_case: UseCase) -> UseCaseVersion:
        """Store a new Use Case version (identical content returns the existing one).
        Never creates an Ontology Version.

        A new version is at once used to judge the latest Ontology Version's structural
        answerability, and that result is stored; a dedupe hit judges nothing again."""
        ...

    def list_use_case_versions(self, knowledge_graph: str) -> list[UseCaseVersion]: ...

    def get_use_case_version(
        self, knowledge_graph: str, number: int | None = None
    ) -> UseCaseVersion:
        """Use Case version `number`, by default the latest. Raises NoUseCaseError when
        the latest is asked for and the Knowledge Graph has no Use Case."""
        ...

    def evaluate_gates(
        self,
        knowledge_graph: str,
        gates: Sequence[Gate],
        *,
        version: int | None = None,
        run: str | None = None,
    ) -> GateResult:
        """Evaluate the Gate definitions (from the repo config) for an Ontology Version
        (default: the latest) or a Construction Run against the stored results, and
        record the outcome together with the definitions used. The outcome is always
        computed here, never taken from the caller."""
        ...

    def list_gate_results(self, knowledge_graph: str) -> list[GateResult]:
        """Every recorded Gate evaluation, oldest first."""
        ...

    def preview_gates(self, knowledge_graph: str) -> list[GatePreview]:
        """A Gate Preview for every Construction Run, in run order: the Gate definitions
        of the latest Gate result about a run (else about any subject) evaluated against
        each run. Records nothing. Empty if the Knowledge Graph was never gated."""
        ...

    def evaluate_consumer_gates(
        self,
        knowledge_graph: str,
        *,
        run: str | None = None,
        version: int | None = None,
        consumer: str | None = None,
    ) -> list[ConsumerGateResult]:
        """Evaluate the Consumer Gates of the latest Use Case Version's Consumers (or of
        `consumer` alone) for a finished run (`run`; else the latest finished run
        standing for `version`; else the latest finished run) against the baseline, and
        record one result per gated Consumer."""
        ...

    def list_consumer_gate_results(
        self, knowledge_graph: str, *, consumer: str | None = None, version: int | None = None
    ) -> list[ConsumerGateResult]:
        """Recorded Consumer Gate results, oldest first, optionally only `consumer`'s or
        only those about a run standing for Ontology Version `version`."""
        ...


class LocalTrackingService:
    def __init__(
        self, store: Store, *, question_mapper: CompetencyQuestionMapper | None = None
    ) -> None:
        """`question_mapper` is the model interface structural answerability uses for
        Competency Questions with neither a Concept mapping nor a query."""
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

    def set_knowledge_graph_description(self, name: str, description: str | None) -> KnowledgeGraph:
        description = description.strip() if description is not None else None
        with self._store.transaction():
            self.get_knowledge_graph(name)
            self._store.set_knowledge_graph_description(name, description or None)
            return self.get_knowledge_graph(name)

    def list_knowledge_graphs(self) -> list[KnowledgeGraphSummary]:
        """All Knowledge Graphs by name, each with its summary."""
        with self._store.transaction():
            return [self._summarise(kg) for kg in self._store.list_knowledge_graphs()]

    def _summarise(self, kg: KnowledgeGraph) -> KnowledgeGraphSummary:
        name = kg.name
        versions = self._store.list_ontology_versions(name)
        runs = self._store.list_runs(name)
        contract = self._store.get_alias(name, self._contract_alias(name))
        return KnowledgeGraphSummary(
            knowledge_graph=kg,
            contract_version=None if contract is None else contract.version,
            latest_version=versions[-1].number if versions else None,
            last_run_status=runs[-1].status if runs else None,
            last_modified_at=self._store.last_change_at(name),
        )

    def register_ontology(self, knowledge_graph: str, ontology: Ontology) -> OntologyVersion:
        with self._store.transaction():
            self.get_knowledge_graph(knowledge_graph)
            return self._register(knowledge_graph, ontology, "registered")

    def _register(
        self,
        knowledge_graph: str,
        ontology: Ontology,
        origin: Origin,
        *,
        base: OntologyVersion | None = None,
    ) -> OntologyVersion:
        """Register `ontology` (deduped by content hash) and run the version built-ins on
        a new version. `base` is the version a Candidate's run consumed."""
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
        self._run_use_case_evaluators(version, base=base)
        return version

    def _candidate_base(self, version: OntologyVersion) -> OntologyVersion | None:
        """The version the run that gave rise to `version` consumed; None unless
        `version` is a run's Candidate."""
        if version.origin != "run":
            return None
        kg = version.knowledge_graph
        run = next(
            (r for r in self._store.list_runs(kg) if r.candidate_version == version.number),
            None,
        )
        return None if run is None else self._store.get_ontology_version(kg, run.ontology_version)

    def _run_use_case_evaluators(
        self,
        version: OntologyVersion,
        use_case_version: int | None = None,
        *,
        base: OntologyVersion | None = None,
    ) -> list[EvaluationResult]:
        """Structural answerability and Competency Question coverage against a Use Case
        version (default: the latest), with regressions judged against the Contract
        Alias's version, and unjustified additions (also without a Use Case). All read
        one Concept mapping, so the mapper runs once. `base` is the version a new
        Candidate's run consumed; otherwise it is looked up."""
        kg = version.knowledge_graph
        if base is None:
            base = self._candidate_base(version)
        try:
            use_case: UseCaseVersion | None = self.get_use_case_version(kg, use_case_version)
        except NoUseCaseError:
            use_case = None
        evaluators: list[OntologyVersionEvaluator] = []
        answerability = None
        if use_case is not None:
            contract_alias = self._store.get_alias(kg, self._contract_alias(kg))
            contract = (
                None
                if contract_alias is None
                else self._store.get_ontology_version(kg, contract_alias.version)
            )
            answerability = StructuralAnswerability(
                use_case.use_case, self._question_mapper, contract
            )
            evaluators += [answerability, CompetencyQuestionCoverage(answerability)]
        evaluators.append(
            UnjustifiedAdditions(answerability, None if base is None else base.ontology)
        )
        return [
            self._store_result(
                kg,
                "ontology_version",
                str(version.number),
                evaluator.name,
                check_evaluation(evaluator.name, evaluator.evaluate(version)),
                use_case_version=None if use_case is None else use_case.number,
            )
            for evaluator in evaluators
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
            return self._run_built_ins(version) + self._run_use_case_evaluators(
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
        if not sdk_side:
            check_not_built_in(evaluator)
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
        return _latest_per_evaluator(
            self._store.list_evaluation_results(knowledge_graph, subject_kind, subject_id)
        )

    def list_evaluation_results(
        self, knowledge_graph: str, subject_kind: SubjectKind
    ) -> list[EvaluationResult]:
        self.get_knowledge_graph(knowledge_graph)
        if subject_kind not in get_args(SubjectKind):
            raise EvaluatorError(f"Unsupported evaluation subject kind {subject_kind!r}")
        by_subject: dict[str, list[EvaluationResult]] = {}
        for result in self._store.list_evaluation_results(knowledge_graph, subject_kind):
            by_subject.setdefault(result.subject_id, []).append(result)
        return [r for results in by_subject.values() for r in _latest_per_evaluator(results)]

    def list_ontology_versions(self, knowledge_graph: str) -> list[OntologyVersion]:
        self.get_knowledge_graph(knowledge_graph)
        return self._store.list_ontology_versions(knowledge_graph)

    def list_candidates(self, knowledge_graph: str) -> list[int]:
        with self._store.transaction():
            versions = self.list_ontology_versions(knowledge_graph)
            pointed_to = {p.to_version for p in self._store.list_promotions(knowledge_graph)}
        return [v.number for v in versions if v.number not in pointed_to]

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

    def start_run(
        self,
        knowledge_graph: str,
        ontology_version: int | None = None,
        *,
        alias: str | None = None,
    ) -> ConstructionRun:
        if ontology_version is not None and alias is not None:
            raise ConflictingArgumentsError(
                "A run consumes an ontology_version or an alias, not both"
            )
        with self._store.transaction():
            if alias is not None:
                ontology_version = self.get_alias(knowledge_graph, alias).version
            elif ontology_version is None:
                ontology_version = self.get_contract_version(knowledge_graph).number
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

    def latest_finished_run(self, knowledge_graph: str, version: int) -> ConstructionRun | None:
        with self._store.transaction():
            self.get_ontology_version(knowledge_graph, version)
            runs = self._finished_runs_standing_for(knowledge_graph, version)
            return runs[-1] if runs else None

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

    def end_run(
        self,
        run_id: str,
        observation: ObservationInput,
        definitions: Mapping[str, str] | None = None,
    ) -> ConstructionRun:
        """Finish the run with the Observation of its Graph Source made at its end."""
        scope, schema = observation
        proposals = check_proposed_definitions(definitions or {})
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
            # Evolution Mode handling, then Conformance: a run introducing new Concepts
            # fails (strict) or gives rise to a Candidate linked to it (evolving). An
            # evolving run is judged against its Candidate, so what it added is the
            # Candidate's Ontology Diff, not a mismatch; any other run against its
            # Declared Ontology.
            declared = self.get_ontology_version(run.knowledge_graph, run.ontology_version)
            judged_against = declared
            status: RunStatus = "finished"
            ignored = tuple(sorted(proposals))
            candidate = candidate_ontology(declared.ontology, schema)
            if candidate is not None:
                if self.get_evolution_mode(run.knowledge_graph) == "strict":
                    status = "failed"
                else:
                    # Proposed Definitions document only what the Candidate adds.
                    candidate, ignored = apply_definitions(declared.ontology, candidate, proposals)
                    judged_against = self._register(
                        run.knowledge_graph, candidate, "run", base=declared
                    )
                    self._store.set_run_candidate(
                        run_id, run.knowledge_graph, judged_against.number
                    )
            self._store.set_run_conformance(
                run_id, assess_conformance(judged_against.ontology, schema)
            )
            self._store.set_run_ignored_definitions(run_id, ignored)
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
            # The latest Ontology Version is judged against the new questions at once.
            ontology_versions = self._store.list_ontology_versions(knowledge_graph)
            if ontology_versions:
                self._run_use_case_evaluators(ontology_versions[-1], version.number)
            return version

    def list_use_case_versions(self, knowledge_graph: str) -> list[UseCaseVersion]:
        self.get_knowledge_graph(knowledge_graph)
        return self._store.list_use_case_versions(knowledge_graph)

    def get_use_case_version(
        self, knowledge_graph: str, number: int | None = None
    ) -> UseCaseVersion:
        self.get_knowledge_graph(knowledge_graph)
        if number is None:
            versions = self._store.list_use_case_versions(knowledge_graph)
            if not versions:
                raise NoUseCaseError(f"Knowledge Graph {knowledge_graph!r} has no Use Case")
            return versions[-1]
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
            contract = self.get_contract_version(knowledge_graph)
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
            alias = Alias(
                knowledge_graph=knowledge_graph, name=name, version=version, updated_at=moved
            )
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
        return self._contract_alias(knowledge_graph)

    def _contract_alias(self, knowledge_graph: str) -> str:
        return self._store.get_contract_alias(knowledge_graph) or DEFAULT_CONTRACT_ALIAS

    def get_contract_version(self, knowledge_graph: str) -> OntologyVersion:
        with self._store.transaction():
            alias = self.get_alias(knowledge_graph, self.get_contract_alias(knowledge_graph))
            return self.get_ontology_version(knowledge_graph, alias.version)

    # --- Gates ----------------------------------------------------------------------

    def evaluate_gates(
        self,
        knowledge_graph: str,
        gates: Sequence[Gate],
        *,
        version: int | None = None,
        run: str | None = None,
    ) -> GateResult:
        if version is not None and run is not None:
            raise ConflictingArgumentsError("Gates are evaluated for a version or a run, not both")
        if not gates:
            raise GateConfigError("No Gates to evaluate")
        with self._store.transaction():
            subject_kind, subject_id, inputs = self._gate_subject(
                knowledge_graph, version=version, run=run
            )
            result = GateResult(
                knowledge_graph=knowledge_graph,
                subject_kind=subject_kind,
                subject_id=subject_id,
                ontology_version=inputs.ontology_version,
                outcomes=run_gates(gates, inputs),
                evaluated_at=_now(),
            )
            self._store.add_gate_result(result)
            return result

    def _gate_subject(
        self, knowledge_graph: str, *, version: int | None, run: str | None
    ) -> tuple[SubjectKind, str, GateInputs]:
        """The subject (a run, else a version, by default the latest) a Gate evaluation
        is about, and its Gate inputs. Reads only: recording is the caller's choice."""
        if run is not None:
            subject = self.get_run(run)
            if subject.knowledge_graph != knowledge_graph:
                raise NotFoundError(
                    f"Knowledge Graph {knowledge_graph!r} has no Construction Run {run!r}"
                )
            number = subject.candidate_version or subject.ontology_version
            return "construction_run", run, self._gate_inputs(knowledge_graph, number, subject)
        if version is None:
            version = self.list_ontology_versions(knowledge_graph)[-1].number
        standing = self._latest_run_standing_for(knowledge_graph, version)
        return (
            "ontology_version",
            str(version),
            self._gate_inputs(knowledge_graph, version, standing),
        )

    def _latest_run_standing_for(
        self, knowledge_graph: str, version: int
    ) -> ConstructionRun | None:
        """The latest run with Conformance whose Candidate (else consumed version) is `version`."""
        runs = [
            r
            for r in self._store.list_runs(knowledge_graph)
            if r.conformance is not None and (r.candidate_version or r.ontology_version) == version
        ]
        return runs[-1] if runs else None

    def _gate_inputs(
        self, knowledge_graph: str, number: int, run: ConstructionRun | None
    ) -> GateInputs:
        contract = self.get_contract_version(knowledge_graph)
        target = self.get_ontology_version(knowledge_graph, number)
        observed = baseline = None
        if run is not None and run.observation_id is not None:
            observations = self._store.list_observations(knowledge_graph)
            index = next(i for i, o in enumerate(observations) if o.id == run.observation_id)
            observed = observations[index].schema
            baseline = observations[index - 1].schema if index > 0 else None
        return GateInputs(
            ontology_version=number,
            contract_version=contract.number,
            diff=diff_ontologies(contract.ontology, target.ontology),
            contract_ontology=contract.ontology,
            ontology=target.ontology,
            conformance=None if run is None else run.conformance,
            evaluations=tuple(
                self.get_evaluation_results(knowledge_graph, "ontology_version", str(number))
            ),
            observed=observed,
            baseline=baseline,
            run_evaluations=()
            if run is None
            else tuple(self.get_evaluation_results(knowledge_graph, "construction_run", run.id)),
        )

    def list_gate_results(self, knowledge_graph: str) -> list[GateResult]:
        self.get_knowledge_graph(knowledge_graph)
        return self._store.list_gate_results(knowledge_graph)

    def preview_gates(self, knowledge_graph: str) -> list[GatePreview]:
        with self._store.transaction():
            results = self.list_gate_results(knowledge_graph)
            if not results:
                return []
            run_results = [r for r in results if r.subject_kind == "construction_run"]
            source = (run_results or results)[-1]
            previews = []
            for run in self._store.list_runs(knowledge_graph):
                _, _, inputs = self._gate_subject(knowledge_graph, version=None, run=run.id)
                previews.append(
                    GatePreview(
                        knowledge_graph=knowledge_graph,
                        subject_kind="construction_run",
                        subject_id=run.id,
                        ontology_version=inputs.ontology_version,
                        outcomes=run_gates(source.gates, inputs),
                        source=GatePreviewSource(
                            subject_kind=source.subject_kind,
                            subject_id=source.subject_id,
                            evaluated_at=source.evaluated_at,
                        ),
                    )
                )
            return previews

    # --- Consumer Gates -------------------------------------------------------------

    def evaluate_consumer_gates(
        self,
        knowledge_graph: str,
        *,
        run: str | None = None,
        version: int | None = None,
        consumer: str | None = None,
    ) -> list[ConsumerGateResult]:
        if run is not None and version is not None:
            raise ConflictingArgumentsError(
                "Consumer Gates judge a run or the run standing for a version, not both"
            )
        with self._store.transaction():
            use_case = self.get_use_case_version(knowledge_graph)
            consumers = use_case.use_case.consumers
            if consumer is not None:
                consumers = tuple(c for c in consumers if c.id == consumer)
                if not consumers:
                    raise NotFoundError(
                        f"Use Case Version {use_case.number} of {knowledge_graph!r} has no "
                        f"Consumer {consumer!r}"
                    )
                if not consumers[0].consumer_gates:
                    raise NoConsumerGatesError(
                        f"Consumer {consumer!r} declares no Consumer Gate in Use Case "
                        f"Version {use_case.number}"
                    )
            gated = [c for c in consumers if c.consumer_gates]
            if not gated:
                raise NoConsumerGatesError(
                    f"No Consumer in Use Case Version {use_case.number} of {knowledge_graph!r} "
                    "declares a Consumer Gate"
                )
            subject = self._consumer_gate_subject(knowledge_graph, run=run, version=version)
            contract = self._contract_version_number(knowledge_graph)
            baseline = (
                None
                if contract is None
                else next(
                    (
                        r
                        for r in reversed(
                            self._finished_runs_standing_for(knowledge_graph, contract)
                        )
                        if r.id != subject.id
                    ),
                    None,
                )
            )
            inputs = ConsumerGateInputs(
                task_questions={t.id: t.competency_questions for c in gated for t in c.tasks},
                candidate=self._question_rows(knowledge_graph, subject),
                baseline=None
                if baseline is None
                else self._question_rows(knowledge_graph, baseline),
                baseline_version=contract,
            )
            evaluated_at = _now()
            results = []
            for c in gated:
                result = ConsumerGateResult(
                    knowledge_graph=knowledge_graph,
                    consumer=c.id,
                    use_case_version=use_case.number,
                    run_id=subject.id,
                    ontology_version=_stands_for(subject),
                    baseline_run_id=None if baseline is None else baseline.id,
                    baseline_ontology_version=contract,
                    outcomes=tuple(evaluate_consumer_gate(g, inputs) for g in c.consumer_gates),
                    evaluated_at=evaluated_at,
                )
                self._store.add_consumer_gate_result(result)
                results.append(result)
            return results

    def _contract_version_number(self, knowledge_graph: str) -> int | None:
        """The Contract Alias's version, None when it points to none: for a Consumer
        Gate that is a missing baseline, recorded as a failure, not an error."""
        alias = self._store.get_alias(knowledge_graph, self._contract_alias(knowledge_graph))
        return None if alias is None else alias.version

    def _consumer_gate_subject(
        self, knowledge_graph: str, *, run: str | None, version: int | None
    ) -> ConstructionRun:
        """The finished run a Consumer Gate evaluation judges."""
        if run is not None:
            subject = self.get_run(run)
            if subject.knowledge_graph != knowledge_graph:
                raise NotFoundError(
                    f"Knowledge Graph {knowledge_graph!r} has no Construction Run {run!r}"
                )
            if subject.status != "finished":
                raise RunNotFinishedError(
                    f"Construction Run {run!r} is {subject.status}, not finished"
                )
            return subject
        if version is not None:
            standing = self.latest_finished_run(knowledge_graph, version)
            if standing is None:
                raise NotFoundError(
                    f"No finished Construction Run of {knowledge_graph!r} stands for Ontology "
                    f"Version {version}"
                )
            return standing
        runs = [r for r in self.list_runs(knowledge_graph) if r.status == "finished"]
        if not runs:
            raise NotFoundError(
                f"Knowledge Graph {knowledge_graph!r} has no finished Construction Run"
            )
        return runs[-1]

    def _finished_runs_standing_for(
        self, knowledge_graph: str, version: int
    ) -> list[ConstructionRun]:
        return [
            r
            for r in self._store.list_runs(knowledge_graph)
            if r.status == "finished" and _stands_for(r) == version
        ]

    def _question_rows(self, knowledge_graph: str, run: ConstructionRun) -> dict[str, QuestionRows]:
        """The row count `competency_question_execution` recorded per question on the run."""
        results = self.get_evaluation_results(knowledge_graph, "construction_run", run.id)
        return {
            question: QuestionRows(rows=e.rows, error=e.status == "error")
            for question, e in executed_questions(results).items()
        }

    def list_consumer_gate_results(
        self, knowledge_graph: str, *, consumer: str | None = None, version: int | None = None
    ) -> list[ConsumerGateResult]:
        self.get_knowledge_graph(knowledge_graph)
        return [
            r
            for r in self._store.list_consumer_gate_results(knowledge_graph)
            if (consumer is None or r.consumer == consumer)
            and (version is None or r.ontology_version == version)
        ]

    def _latest_gate_verdict(self, knowledge_graph: str, version: int) -> str | None:
        """ "passed"/"failed" for the version's latest Gate result; None if never gated."""
        for result in reversed(self._store.list_gate_results(knowledge_graph)):
            if result.ontology_version == version:
                return "passed" if result.passed else "failed"
        return None


def _latest_per_evaluator(results: Sequence[EvaluationResult]) -> list[EvaluationResult]:
    """One subject's results, oldest first -> the latest per (Evaluator, parameters),
    ordered by Evaluator name then parameters."""
    latest = {(r.evaluator, json.dumps(r.parameters, sort_keys=True)): r for r in results}
    return [latest[key] for key in sorted(latest)]


def _stands_for(run: ConstructionRun) -> int:
    """The Ontology Version a run stands for: its Candidate, else the version it consumed."""
    return run.candidate_version or run.ontology_version


def _now() -> datetime:
    return datetime.now(UTC)
