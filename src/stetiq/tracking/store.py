"""Metadata store interface: persistence only, no domain rules.

Domain rules (dedupe, numbering, validation) live in `LocalTrackingService`.
Implementation: `SqlStore` (SQLite or Postgres; used by local mode and the server).
"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

from stetiq.graph_source import GraphSourceScope
from stetiq.tracking.entities import (
    ConstructionRun,
    EvaluationResult,
    KnowledgeGraph,
    Observation,
    OntologyVersion,
    RunStatus,
    UseCaseVersion,
)


class Store(Protocol):
    def add_knowledge_graph(self, kg: KnowledgeGraph) -> None:
        """Raises KnowledgeGraphAlreadyExistsError if the name is taken."""

    def get_knowledge_graph(self, name: str) -> KnowledgeGraph | None: ...

    def add_ontology_version(self, version: OntologyVersion) -> None:
        """Insert-only: Ontology Versions are immutable, there is no update."""

    def get_ontology_version(self, knowledge_graph: str, number: int) -> OntologyVersion | None: ...

    def find_ontology_version_by_hash(
        self, knowledge_graph: str, content_hash: str
    ) -> OntologyVersion | None: ...

    def list_ontology_versions(self, knowledge_graph: str) -> list[OntologyVersion]:
        """Ordered by version number ascending."""

    def set_graph_source(self, knowledge_graph: str, scope: GraphSourceScope) -> None:
        """Bind (or rebind) the Knowledge Graph's Graph Source scope."""

    def get_graph_source(self, knowledge_graph: str) -> GraphSourceScope | None: ...

    def add_run(self, run: ConstructionRun) -> None: ...

    def get_run(self, run_id: str) -> ConstructionRun | None: ...

    def list_runs(self, knowledge_graph: str) -> list[ConstructionRun]:
        """Ordered by start time ascending."""

    def set_run_params(self, run_id: str, params: dict[str, str]) -> None:
        """Upsert: a key logged again takes the new value."""

    def set_run_metrics(self, run_id: str, metrics: dict[str, float]) -> None:
        """Upsert: a key logged again takes the new value."""

    def end_run(
        self, run_id: str, status: RunStatus, ended_at: datetime, observation_id: str | None
    ) -> None: ...

    def add_observation(self, observation: Observation) -> None: ...

    def get_observation(self, observation_id: str) -> Observation | None: ...

    def list_observations(self, knowledge_graph: str) -> list[Observation]:
        """Ordered by observation time ascending."""

    def add_evaluation_result(self, result: EvaluationResult) -> None:
        """Insert-only: re-running an Evaluator adds a newer result."""

    def list_evaluation_results(
        self, knowledge_graph: str, subject_kind: str, subject_id: str
    ) -> list[EvaluationResult]:
        """Every stored result for the subject, oldest first."""

    def add_use_case_version(self, version: UseCaseVersion) -> None:
        """Insert-only: Use Case versions are immutable."""

    def get_use_case_version(self, knowledge_graph: str, number: int) -> UseCaseVersion | None: ...

    def find_use_case_version_by_hash(
        self, knowledge_graph: str, content_hash: str
    ) -> UseCaseVersion | None: ...

    def list_use_case_versions(self, knowledge_graph: str) -> list[UseCaseVersion]:
        """Ordered by version number ascending."""

    def transaction(self):
        """Context manager making the enclosed store calls atomic."""
