"""The public Python SDK."""

from __future__ import annotations

import getpass
import os
import subprocess
import tempfile
from collections.abc import Sequence
from pathlib import Path

from stetiq.entry_point import EntryPoint, EntryPointError, placeholder_values
from stetiq.errors import (
    EvaluatorError,
    GraphSourceUnavailableError,
    NotFoundError,
    UseCaseValidationError,
)
from stetiq.evaluation.framework import (
    Evaluator,
    OntologyVersionEvaluator,
    check_evaluation,
    check_evaluator,
)
from stetiq.evaluation.answerability import ANSWERABILITY_EVALUATOR
from stetiq.evaluation.structural import BUILT_IN_EVALUATORS
from stetiq.gates import GateInputs, GatesInput, evaluate_gates, load_gates
from stetiq.graph_source import GraphSource, GraphSourceScope, graph_source_from_env
from stetiq.ontology import Ontology, parse_yaml
from stetiq.ontology.yaml_format import to_yaml
from stetiq.ontology.diff import OntologyDiff, diff_ontologies
from stetiq.tracking import (
    Alias,
    Promotion,
    ConstructionRun,
    EvaluationResult,
    GateResult,
    KnowledgeGraph,
    LocalTrackingService,
    Observation,
    OntologyVersion,
    RemoteTrackingService,
    RunComparison,
    SqlStore,
    TrackingService,
    UseCaseVersion,
)
from stetiq.use_case import (
    CompetencyQuestion,
    UseCase,
    check_question,
    parse_use_case_dict,
    parse_use_case_yaml,
)
from stetiq.drift import DriftThresholds
from stetiq.tracking.entities import DriftEvent, EvolutionMode, ObservationOutcome

TRACKING_URI_ENV = "STETIQ_TRACKING_URI"
DEFAULT_TRACKING_URI = "sqlite:///.stetiq/stetiq.db"
ACTOR_ENV = "STETIQ_ACTOR"
TOKEN_ENV = "STETIQ_TOKEN"


def resolve_actor(actor: str | None = None) -> str:
    """Who the audit log records for Alias moves in local mode: `actor`, else $STETIQ_ACTOR,
    else the OS user. (In server mode the server records the API token's user instead.)"""
    if actor or os.environ.get(ACTOR_ENV):
        return actor or os.environ[ACTOR_ENV]
    try:
        return getpass.getuser()
    except Exception:
        return "unknown"

# A Declared Ontology given to the SDK: stetiq YAML text, a path to a YAML file,
# or an already-built Ontology model.
OntologyInput = str | os.PathLike[str] | Ontology


def resolve_tracking_uri(tracking_uri: str | None = None) -> str:
    return tracking_uri or os.environ.get(TRACKING_URI_ENV) or DEFAULT_TRACKING_URI


def resolve_token(token: str | None = None) -> str | None:
    """The API token for server mode: `token`, else $STETIQ_TOKEN (local mode needs none)."""
    return token or os.environ.get(TOKEN_ENV) or None


def service_for_uri(tracking_uri: str, *, token: str | None = None) -> TrackingService:
    """Pick the mode from the tracking URI.

    - `http://` / `https://`: remote mode, talking to a stetiq server with API `token`
    - `sqlite:///<path>`, `postgresql[+psycopg]://...`: local mode, in-process over that
      database (tokenless: `token` is ignored)
    """
    scheme = tracking_uri.split(":", 1)[0].lower()
    if scheme in ("http", "https"):
        return RemoteTrackingService(tracking_uri, token=resolve_token(token))
    if scheme == "sqlite" or scheme.startswith("postgresql"):
        return LocalTrackingService(SqlStore(tracking_uri))
    raise ValueError(
        f"Unsupported tracking URI {tracking_uri!r} "
        "(expected http(s)://<server>, sqlite:///<path> or postgresql://...)"
    )


def _to_ontology(ontology: OntologyInput) -> Ontology:
    if isinstance(ontology, Ontology):
        return ontology
    if isinstance(ontology, os.PathLike):
        return parse_yaml(Path(ontology).read_text(encoding="utf-8"))
    return parse_yaml(ontology)

# A Use Case given to the SDK: Use Case YAML text, a path to a YAML file, a `UseCase`,
# or just its Competency Questions.
UseCaseInput = str | os.PathLike[str] | UseCase | list[CompetencyQuestion] | tuple[CompetencyQuestion, ...]


def _to_use_case(use_case: UseCaseInput) -> UseCase:
    if isinstance(use_case, UseCase):
        return use_case
    if isinstance(use_case, (list, tuple)):
        return UseCase(competency_questions=tuple(use_case))
    if isinstance(use_case, os.PathLike):
        return parse_use_case_yaml(Path(use_case).read_text(encoding="utf-8"))
    return parse_use_case_yaml(use_case)


def _to_question(question: CompetencyQuestion | dict) -> CompetencyQuestion:
    if isinstance(question, CompetencyQuestion):
        return check_question(question)
    return parse_use_case_dict({"competency_questions": [question]}).competency_questions[0]


class Client:
    """Entry point to stetiq: remote mode for `http(s)://` tracking URIs, else local mode."""

    def __init__(
        self,
        tracking_uri: str | None = None,
        *,
        service: TrackingService | None = None,
        graph_source: GraphSource | None = None,
        actor: str | None = None,
        token: str | None = None,
    ) -> None:
        """`graph_source` is the adapter (e.g. Neo4j, with its credentials) used to observe
        the bound Graph Source scope when a Construction Run ends. It runs in this
        process: the stetiq server never connects to the graph database. Without it, a
        Neo4j adapter is built on first use from `$STETIQ_GRAPH_SOURCE_URI` (plus
        `$STETIQ_GRAPH_SOURCE_USER` / `$STETIQ_GRAPH_SOURCE_PASSWORD`).

        `token` (else $STETIQ_TOKEN) is the API token server mode requires; local mode
        ignores it. In server mode the audit log records the token's user, not `actor`."""
        self.tracking_uri = resolve_tracking_uri(tracking_uri)
        self._service = service or service_for_uri(self.tracking_uri, token=token)
        self._graph_source = graph_source
        self.actor = resolve_actor(actor)
        # Custom Evaluators run in this process (the user's code), in every mode;
        # only their results go to the tracking service.
        self._evaluators: dict[str, Evaluator] = {}

    def create_knowledge_graph(
        self, name: str, ontology: OntologyInput | None = None
    ) -> KnowledgeGraph:
        """Create a Knowledge Graph; its Declared Ontology becomes Ontology Version 1."""
        declared = None if ontology is None else _to_ontology(ontology)
        kg = self._service.create_knowledge_graph(name, declared)
        if self._evaluators:
            self._run_custom_evaluators(self._service.get_ontology_version(name, 1))
        return kg

    def get_knowledge_graph(self, name: str) -> KnowledgeGraph:
        return self._service.get_knowledge_graph(name)

    def register_ontology(self, knowledge_graph: str, ontology: OntologyInput) -> OntologyVersion:
        """Register an Ontology by hand; identical content returns the existing version."""
        version = self._service.register_ontology(knowledge_graph, _to_ontology(ontology))
        # Identical content returns an existing version: only fill in missing results.
        self._run_custom_evaluators(version, only_missing=True)
        return version

    def list_ontology_versions(self, knowledge_graph: str) -> list[OntologyVersion]:
        return self._service.list_ontology_versions(knowledge_graph)

    def get_ontology_version(self, knowledge_graph: str, number: int) -> OntologyVersion:
        return self._service.get_ontology_version(knowledge_graph, number)

    def get_ontology_yaml(self, knowledge_graph: str, number: int) -> str:
        return self.get_ontology_version(knowledge_graph, number).to_yaml()

    def get_evaluation_results(
        self, knowledge_graph: str, version: int
    ) -> list[EvaluationResult]:
        """The latest result of every Evaluator (built-in and custom) for an Ontology Version."""
        return self._service.get_evaluation_results(knowledge_graph, "ontology_version", str(version))

    def evaluate(
        self,
        knowledge_graph: str,
        version: int,
        *,
        evaluators: Sequence[OntologyVersionEvaluator] = (),
        use_case_version: int | None = None,
    ) -> list[EvaluationResult]:
        """Re-run every Evaluator (built-in and this client's custom ones) on a version.

        `evaluators` are extra, one-off Evaluators for this call only (not
        registered), e.g. a parameterised `GoldOntologyAlignment(gold_version)`
        whose reference is chosen per evaluation.

        Structural answerability is judged against `use_case_version` (default: the
        Knowledge Graph's latest Use Case version), which its result records.

        Results are stored as the newest per Evaluator (and parameters); returns
        the latest of all.
        """
        reserved = {e.name for e in BUILT_IN_EVALUATORS} | {ANSWERABILITY_EVALUATOR}
        for evaluator in evaluators:
            check_evaluator(evaluator)
            if not isinstance(evaluator, OntologyVersionEvaluator):
                raise EvaluatorError(f"{evaluator.name!r} is not an OntologyVersionEvaluator")
            if evaluator.name in reserved:
                raise EvaluatorError(f"An Evaluator named {evaluator.name!r} is already registered")
        self._service.evaluate_ontology_version(knowledge_graph, version, use_case_version)
        extra = list(evaluators)
        if self._evaluators or extra:
            self._run_custom_evaluators(
                self._service.get_ontology_version(knowledge_graph, version), extra=extra
            )
        return self.get_evaluation_results(knowledge_graph, version)

    def register_evaluator(self, evaluator: Evaluator) -> None:
        """Register a custom Evaluator with this client.

        An `OntologyVersionEvaluator` then runs on every Ontology Version this
        client creates and on `evaluate()`; its results are stored alongside the
        built-ins. `ConstructionRunEvaluator`s are accepted for run-level evaluation.
        """
        check_evaluator(evaluator)
        taken = {e.name for e in BUILT_IN_EVALUATORS} | {ANSWERABILITY_EVALUATOR} | set(self._evaluators)
        if evaluator.name in taken:
            raise EvaluatorError(f"An Evaluator named {evaluator.name!r} is already registered")
        self._evaluators[evaluator.name] = evaluator

    def _run_custom_evaluators(
        self,
        version: OntologyVersion,
        *,
        only_missing: bool = False,
        extra: Sequence[OntologyVersionEvaluator] = (),
    ) -> list[EvaluationResult]:
        evaluators = [
            e for e in self._evaluators.values() if isinstance(e, OntologyVersionEvaluator)
        ] + list(extra)
        if not evaluators:
            return []
        subject_id = str(version.number)
        if only_missing:
            done = {
                r.evaluator
                for r in self._service.get_evaluation_results(
                    version.knowledge_graph, "ontology_version", subject_id
                )
            }
            evaluators = [e for e in evaluators if e.name not in done]
        results = []
        for evaluator in evaluators:
            try:
                outcome = evaluator.evaluate(version)
            except Exception as exc:
                raise EvaluatorError(
                    f"Evaluator {evaluator.name!r} failed on {version.knowledge_graph} "
                    f"Ontology Version {version.number}: {exc}"
                ) from exc
            results.append(
                self._service.record_evaluation(
                    version.knowledge_graph,
                    "ontology_version",
                    subject_id,
                    evaluator.name,
                    check_evaluation(evaluator.name, outcome),
                    evaluator.parameters,
                )
            )
        return results

    def diff_ontology_versions(
        self, knowledge_graph: str, base: int | None = None, target: int | None = None
    ) -> OntologyDiff:
        """The Ontology Diff from version `base` to version `target`, each change classified.

        `base` defaults to the Contract Alias's version and `target` to the latest
        version, so a bare call answers "what would promoting the newest version change"."""
        if base is None:
            base = self.get_contract_version(knowledge_graph).number
        if target is None:
            target = self.list_ontology_versions(knowledge_graph)[-1].number
        return diff_ontologies(
            self.get_ontology_version(knowledge_graph, base).ontology,
            self.get_ontology_version(knowledge_graph, target).ontology,
        )

    def diff_ontologies(self, base: OntologyInput, target: OntologyInput) -> OntologyDiff:
        """The Ontology Diff between two Ontologies that need not be registered (e.g. files in a repo)."""
        return diff_ontologies(_to_ontology(base), _to_ontology(target))

    # --- Use Cases ------------------------------------------------------------------

    def register_use_case(self, knowledge_graph: str, use_case: UseCaseInput) -> UseCaseVersion:
        """Register the Knowledge Graph's Use Case as a new Use Case version.

        Use Case versions are numbered independently of Ontology Versions; identical
        content returns the existing version."""
        return self._service.register_use_case(knowledge_graph, _to_use_case(use_case))

    def add_competency_question(
        self, knowledge_graph: str, question: CompetencyQuestion | dict
    ) -> UseCaseVersion:
        """Add a Competency Question to the latest Use Case, creating a new Use Case version
        (version 1 if the Knowledge Graph has no Use Case yet)."""
        question = _to_question(question)
        versions = self._service.list_use_case_versions(knowledge_graph)
        current = versions[-1].use_case if versions else UseCase(competency_questions=())
        if any(q.id == question.id for q in current.competency_questions):
            raise UseCaseValidationError(
                f"{question.id}: the Use Case already has a Competency Question with this id"
            )
        return self._service.register_use_case(
            knowledge_graph,
            UseCase(
                competency_questions=(*current.competency_questions, question),
                description=current.description,
            ),
        )

    def list_use_case_versions(self, knowledge_graph: str) -> list[UseCaseVersion]:
        return self._service.list_use_case_versions(knowledge_graph)

    def get_use_case_version(self, knowledge_graph: str, number: int) -> UseCaseVersion:
        return self._service.get_use_case_version(knowledge_graph, number)

    # --- Gates ----------------------------------------------------------------------

    def evaluate_gates(
        self,
        knowledge_graph: str,
        gates: GatesInput,
        *,
        version: int | None = None,
        run: str | None = None,
    ) -> GateResult:
        """Evaluate Gates (a config file path, config YAML text, or Gate objects) for an
        Ontology Version (default: the latest, e.g. a fresh Candidate) or a Construction
        Run, against the results stored on the server. The result, with the Gate
        definitions used, is recorded there and returned.

        What the Gates see, for the version the subject stands for (a run stands for its
        Candidate, else the version it consumed):
        - the Ontology Diff from the Contract Alias's version to it;
        - its latest Evaluator results;
        - Conformance and Observed Schema of the run (for a version: the latest
          finished-or-strict-failed run standing for it), and the Observation before
          that run's as statistics baseline.
        """
        if version is not None and run is not None:
            raise ValueError("evaluate_gates takes version or run, not both")
        definitions = load_gates(gates)
        if run is not None:
            subject = self.get_run(run)
            if subject.knowledge_graph != knowledge_graph:
                raise NotFoundError(
                    f"Knowledge Graph {knowledge_graph!r} has no Construction Run {run!r}"
                )
            number = subject.candidate_version or subject.ontology_version
        else:
            number = version or self.list_ontology_versions(knowledge_graph)[-1].number
            subject = self._latest_run_standing_for(knowledge_graph, number)
        outcomes = evaluate_gates(definitions, self._gate_inputs(knowledge_graph, number, subject))
        if run is not None:
            return self._service.record_gate_result(knowledge_graph, "construction_run", run, outcomes)
        return self._service.record_gate_result(
            knowledge_graph, "ontology_version", str(number), outcomes
        )

    def _latest_run_standing_for(self, knowledge_graph: str, version: int) -> ConstructionRun | None:
        runs = [
            r
            for r in self.list_runs(knowledge_graph)
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
            observations = self.list_observations(knowledge_graph)
            index = next(i for i, o in enumerate(observations) if o.id == run.observation_id)
            observed = observations[index].schema
            baseline = observations[index - 1].schema if index > 0 else None
        return GateInputs(
            ontology_version=number,
            contract_version=contract.number,
            diff=diff_ontologies(contract.ontology, target.ontology),
            conformance=None if run is None else run.conformance,
            evaluations=tuple(self.get_evaluation_results(knowledge_graph, number)),
            observed=observed,
            baseline=baseline,
        )

    def list_gate_results(self, knowledge_graph: str) -> list[GateResult]:
        """Every recorded Gate evaluation of the Knowledge Graph, oldest first, each with
        the Gate definitions it used."""
        return self._service.list_gate_results(knowledge_graph)

    # --- Aliases and Promotion ------------------------------------------------------

    def set_alias(self, knowledge_graph: str, alias: str, version: int) -> Alias:
        """Create `alias` or move it to `version` (Promotion, or rollback to an earlier
        version). Never blocked by Gates; every move is audit-logged with this
        client's actor."""
        return self._service.set_alias(knowledge_graph, alias, version, self.actor)

    def get_alias(self, knowledge_graph: str, alias: str) -> Alias:
        return self._service.get_alias(knowledge_graph, alias)

    def list_aliases(self, knowledge_graph: str) -> list[Alias]:
        """The Knowledge Graph's Aliases, by name."""
        return self._service.list_aliases(knowledge_graph)

    def get_ontology_version_by_alias(self, knowledge_graph: str, alias: str) -> OntologyVersion:
        """The Ontology Version `alias` currently points to, e.g. for a downstream consumer."""
        return self.get_ontology_version(knowledge_graph, self.get_alias(knowledge_graph, alias).version)

    def list_promotions(self, knowledge_graph: str) -> list[Promotion]:
        """The Alias audit log: every Alias move, oldest first."""
        return self._service.list_promotions(knowledge_graph)

    def set_contract_alias(self, knowledge_graph: str, alias: str) -> None:
        """Designate which existing Alias is the Contract Alias (default `production`)."""
        self._service.set_contract_alias(knowledge_graph, alias)

    def get_contract_alias(self, knowledge_graph: str) -> str:
        return self._service.get_contract_alias(knowledge_graph)

    def get_contract_version(self, knowledge_graph: str) -> OntologyVersion:
        """The Ontology Version the Contract Alias points to."""
        return self.get_ontology_version_by_alias(
            knowledge_graph, self.get_contract_alias(knowledge_graph)
        )

    # --- Graph Sources --------------------------------------------------------------

    def bind_graph_source(self, knowledge_graph: str, scope: GraphSourceScope) -> None:
        """Bind the Knowledge Graph to a Graph Source scope (replacing any earlier one)."""
        self._service.bind_graph_source(knowledge_graph, scope)

    def get_graph_source(self, knowledge_graph: str) -> GraphSourceScope:
        return self._service.get_graph_source(knowledge_graph)

    # --- Evolution Mode -------------------------------------------------------------

    def set_evolution_mode(self, knowledge_graph: str, mode: EvolutionMode) -> None:
        """What ending a run that introduces new Concepts does: "strict" fails the run,
        "evolving" (the default) creates a Candidate Ontology Version linked to it."""
        self._service.set_evolution_mode(knowledge_graph, mode)

    def get_evolution_mode(self, knowledge_graph: str) -> EvolutionMode:
        return self._service.get_evolution_mode(knowledge_graph)

    # --- Construction Runs ----------------------------------------------------------

    def start_run(
        self,
        knowledge_graph: str,
        *,
        ontology_version: int | None = None,
        alias: str | None = None,
    ) -> ActiveRun:
        """Start a Construction Run. Its Declared Ontology is `ontology_version`, or the
        version `alias` points to, or by default the Contract Alias's version.

        Use the result as a context manager: leaving the block ends the run (which
        observes the Graph Source); an exception inside it marks the run failed."""
        if ontology_version is not None and alias is not None:
            raise ValueError("start_run takes ontology_version or alias, not both")
        graph_source = self._require_graph_source()
        if ontology_version is None:
            alias = alias or self.get_contract_alias(knowledge_graph)
            ontology_version = self.get_alias(knowledge_graph, alias).version
        run = self._service.start_run(knowledge_graph, ontology_version)
        declared = self._service.get_ontology_version(knowledge_graph, ontology_version)
        return ActiveRun(self._service, graph_source, run, declared.ontology)

    def _require_graph_source(self) -> GraphSource:
        if self._graph_source is None:
            self._graph_source = graph_source_from_env()
        if self._graph_source is None:
            raise GraphSourceUnavailableError(
                "Client has no Graph Source adapter to observe with; pass graph_source=... "
                "or set STETIQ_GRAPH_SOURCE_URI"
            )
        return self._graph_source

    def run_entry_point(
        self,
        knowledge_graph: str,
        entry_point: EntryPoint,
        *,
        ontology_version: int | None = None,
        alias: str | None = None,
        cwd: str | os.PathLike[str] | None = None,
    ) -> ConstructionRun:
        """Invoke the Construction Entry Point as a Construction Run (what `stetiq run` does).

        The Declared Ontology (chosen as for `start_run`) is written to a temporary file
        and the command runs with its placeholders filled in, inheriting this process's
        environment and output streams. A zero exit ends the run the same way SDK
        instrumentation does (Observation, Conformance, Evolution Mode); a non-zero exit
        fails the run without observing, so it never yields a Candidate. The exit code
        is logged as the run param `entry_point.exit_code`. Returns the final run:
        check `status`, since a strict Evolution Mode can also fail it."""
        with self.start_run(knowledge_graph, ontology_version=ontology_version, alias=alias) as run:
            with tempfile.TemporaryDirectory(prefix="stetiq-run-") as tmp:
                ontology_path = Path(tmp) / f"declared-ontology-v{run.ontology_version}.yaml"
                ontology_path.write_text(to_yaml(run.declared_ontology))
                scope = self._service.get_graph_source(knowledge_graph)
                argv = entry_point.argv(
                    placeholder_values(
                        ontology_path=str(ontology_path),
                        scope=scope,
                        knowledge_graph=knowledge_graph,
                        ontology_version=run.ontology_version,
                        run_id=run.id,
                    )
                )
                try:
                    exit_code = subprocess.run(argv, cwd=cwd).returncode
                except OSError as e:
                    raise EntryPointError(f"could not start the Construction Entry Point {argv[0]!r}: {e}") from e
            run.log_param("entry_point.exit_code", exit_code)
            if exit_code != 0:
                run.fail()
        return self.get_run(run.id)

    def get_run(self, run_id: str) -> ConstructionRun:
        return self._service.get_run(run_id)

    def list_runs(self, knowledge_graph: str) -> list[ConstructionRun]:
        """All Construction Runs of the Knowledge Graph, oldest first."""
        return self._service.list_runs(knowledge_graph)

    def compare_runs(self, run_ids: list[str]) -> RunComparison:
        """Runs side by side: their params, metrics and consumed Ontology Versions."""
        runs = tuple(self.get_run(i) for i in run_ids)
        param_keys = sorted({k for r in runs for k in r.params})
        metric_keys = sorted({k for r in runs for k in r.metrics})
        return RunComparison(
            runs=runs,
            params={k: tuple(r.params.get(k) for r in runs) for k in param_keys},
            metrics={k: tuple(r.metrics.get(k) for r in runs) for k in metric_keys},
        )

    # --- Observations ---------------------------------------------------------------

    def get_observation(self, observation_id: str) -> Observation:
        return self._service.get_observation(observation_id)

    def list_observations(self, knowledge_graph: str) -> list[Observation]:
        """All Observations of the Knowledge Graph's Graph Source, oldest first."""
        return self._service.list_observations(knowledge_graph)

    def observe(
        self, knowledge_graph: str, *, thresholds: DriftThresholds | None = None
    ) -> ObservationOutcome:
        """Observe the bound Graph Source scope now, outside any Construction Run (what
        `stetiq observe` does; schedule it with cron, Airflow or CI).

        The Observation is compared with the Contract Alias's Ontology Version
        (structural Drift) and with the previous Observation (statistical Drift, only
        beyond `thresholds`). Drift raises a Drift event, returned and listed by
        `list_drift_events`; it never creates an Ontology Version."""
        graph_source = self._require_graph_source()
        scope = self._service.get_graph_source(knowledge_graph)
        schema = graph_source.observe(scope)
        return self._service.record_observation(knowledge_graph, (scope, schema), thresholds)

    def list_drift_events(self, knowledge_graph: str) -> list[DriftEvent]:
        """The Knowledge Graph's Drift events, oldest first."""
        return self._service.list_drift_events(knowledge_graph)


class ActiveRun:
    """A running Construction Run, as handed to the user's pipeline by `start_run`."""

    def __init__(
        self,
        service: TrackingService,
        graph_source: GraphSource,
        run: ConstructionRun,
        declared_ontology: Ontology,
    ) -> None:
        self._service = service
        self._graph_source = graph_source
        self.id = run.id
        self.knowledge_graph = run.knowledge_graph
        self.ontology_version = run.ontology_version
        self.declared_ontology = declared_ontology

    def log_param(self, key: str, value: object) -> None:
        self.log_params({key: value})

    def log_params(self, params: dict[str, object]) -> None:
        """Params are stored as strings; logging a key again replaces its value."""
        self._service.log_params(self.id, {k: str(v) for k, v in params.items()})

    def log_metric(self, key: str, value: float) -> None:
        self.log_metrics({key: value})

    def log_metrics(self, metrics: dict[str, float]) -> None:
        """Logging a key again replaces its value."""
        self._service.log_metrics(self.id, {k: float(v) for k, v in metrics.items()})

    def end(self) -> ConstructionRun:
        """End the run: observe the whole bound Graph Source scope and store the
        Observed Schema. If the Observation fails, the run is marked failed."""
        try:
            scope = self._service.get_graph_source(self.knowledge_graph)
            schema = self._graph_source.observe(scope)
        except BaseException:
            self._service.fail_run(self.id)
            raise
        return self._service.end_run(self.id, (scope, schema))

    def fail(self) -> ConstructionRun:
        """Abort the run; it is recorded as failed and nothing is observed."""
        return self._service.fail_run(self.id)

    def __enter__(self) -> ActiveRun:
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if self._service.get_run(self.id).status != "running":
            return  # ended or failed explicitly inside the block
        if exc_type is None:
            self.end()
        else:
            self.fail()
