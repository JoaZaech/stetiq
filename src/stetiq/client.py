"""The public Python SDK."""

from __future__ import annotations

import os
from pathlib import Path

from stetiq.errors import EvaluatorError
from stetiq.evaluation.framework import (
    Evaluator,
    OntologyVersionEvaluator,
    check_evaluation,
    check_evaluator,
)
from stetiq.evaluation.structural import BUILT_IN_EVALUATORS
from stetiq.ontology import Ontology, parse_yaml
from stetiq.tracking import (
    EvaluationResult,
    KnowledgeGraph,
    LocalTrackingService,
    OntologyVersion,
    RemoteTrackingService,
    SqlStore,
    TrackingService,
)

TRACKING_URI_ENV = "STETIQ_TRACKING_URI"
DEFAULT_TRACKING_URI = "sqlite:///.stetiq/stetiq.db"

# A Declared Ontology given to the SDK: stetiq YAML text, a path to a YAML file,
# or an already-built Ontology model.
OntologyInput = str | os.PathLike[str] | Ontology


def resolve_tracking_uri(tracking_uri: str | None = None) -> str:
    return tracking_uri or os.environ.get(TRACKING_URI_ENV) or DEFAULT_TRACKING_URI


def service_for_uri(tracking_uri: str) -> TrackingService:
    """Pick the mode from the tracking URI.

    - `http://` / `https://`: remote mode, talking to a stetiq server
    - `sqlite:///<path>`, `postgresql[+psycopg]://...`: local mode, in-process over that database
    """
    scheme = tracking_uri.split(":", 1)[0].lower()
    if scheme in ("http", "https"):
        return RemoteTrackingService(tracking_uri)
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


class Client:
    """Entry point to stetiq: remote mode for `http(s)://` tracking URIs, else local mode."""

    def __init__(
        self, tracking_uri: str | None = None, *, service: TrackingService | None = None
    ) -> None:
        self.tracking_uri = resolve_tracking_uri(tracking_uri)
        self._service = service or service_for_uri(self.tracking_uri)
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

    def evaluate(self, knowledge_graph: str, version: int) -> list[EvaluationResult]:
        """Re-run every Evaluator (built-in and this client's custom ones) on a version.

        Results are stored as the newest per Evaluator; returns the latest of all.
        """
        self._service.evaluate_ontology_version(knowledge_graph, version)
        if self._evaluators:
            self._run_custom_evaluators(self._service.get_ontology_version(knowledge_graph, version))
        return self.get_evaluation_results(knowledge_graph, version)

    def register_evaluator(self, evaluator: Evaluator) -> None:
        """Register a custom Evaluator with this client.

        An `OntologyVersionEvaluator` then runs on every Ontology Version this
        client creates and on `evaluate()`; its results are stored alongside the
        built-ins. `ConstructionRunEvaluator`s are accepted for run-level evaluation.
        """
        check_evaluator(evaluator)
        taken = {e.name for e in BUILT_IN_EVALUATORS} | set(self._evaluators)
        if evaluator.name in taken:
            raise EvaluatorError(f"An Evaluator named {evaluator.name!r} is already registered")
        self._evaluators[evaluator.name] = evaluator

    def _run_custom_evaluators(
        self, version: OntologyVersion, *, only_missing: bool = False
    ) -> list[EvaluationResult]:
        evaluators = [
            e for e in self._evaluators.values() if isinstance(e, OntologyVersionEvaluator)
        ]
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
                )
            )
        return results
