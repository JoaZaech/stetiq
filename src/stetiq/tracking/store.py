"""Metadata store interface: persistence only, no domain rules.

Domain rules (dedupe, numbering, validation) live in `LocalTrackingService`.
Implementations: `SqliteStore` (local mode); Postgres comes with the server.
"""

from __future__ import annotations

from typing import Protocol

from stetiq.tracking.entities import KnowledgeGraph, OntologyVersion


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

    def transaction(self):
        """Context manager making the enclosed store calls atomic."""
