"""The public Python SDK."""

from __future__ import annotations

import os
from pathlib import Path

from stetiq.ontology import Ontology, parse_yaml
from stetiq.tracking import (
    KnowledgeGraph,
    LocalTrackingService,
    OntologyVersion,
    SqliteStore,
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
    if tracking_uri.startswith("sqlite:///"):
        return LocalTrackingService(SqliteStore(tracking_uri.removeprefix("sqlite:///")))
    raise ValueError(f"Unsupported tracking URI {tracking_uri!r} (expected sqlite:///<path>)")


def _to_ontology(ontology: OntologyInput) -> Ontology:
    if isinstance(ontology, Ontology):
        return ontology
    if isinstance(ontology, os.PathLike):
        return parse_yaml(Path(ontology).read_text(encoding="utf-8"))
    return parse_yaml(ontology)


class Client:
    """Entry point to stetiq. Local mode (in-process SQLite) for `sqlite:///` URIs."""

    def __init__(
        self, tracking_uri: str | None = None, *, service: TrackingService | None = None
    ) -> None:
        self.tracking_uri = resolve_tracking_uri(tracking_uri)
        self._service = service or service_for_uri(self.tracking_uri)

    def create_knowledge_graph(
        self, name: str, ontology: OntologyInput | None = None
    ) -> KnowledgeGraph:
        """Create a Knowledge Graph; its Declared Ontology becomes Ontology Version 1."""
        declared = None if ontology is None else _to_ontology(ontology)
        return self._service.create_knowledge_graph(name, declared)

    def get_knowledge_graph(self, name: str) -> KnowledgeGraph:
        return self._service.get_knowledge_graph(name)

    def register_ontology(self, knowledge_graph: str, ontology: OntologyInput) -> OntologyVersion:
        """Register an Ontology by hand; identical content returns the existing version."""
        return self._service.register_ontology(knowledge_graph, _to_ontology(ontology))

    def list_ontology_versions(self, knowledge_graph: str) -> list[OntologyVersion]:
        return self._service.list_ontology_versions(knowledge_graph)

    def get_ontology_version(self, knowledge_graph: str, number: int) -> OntologyVersion:
        return self._service.get_ontology_version(knowledge_graph, number)

    def get_ontology_yaml(self, knowledge_graph: str, number: int) -> str:
        return self.get_ontology_version(knowledge_graph, number).to_yaml()
