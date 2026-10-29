"""Tracking entities returned by the SDK. Plain immutable values, no store handles."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from stetiq.ontology import Ontology, to_yaml

# "registered": registered by hand; "run": created as a Candidate by a Construction Run (later ticket).
Origin = Literal["registered", "run"]


@dataclass(frozen=True)
class KnowledgeGraph:
    name: str
    created_at: datetime


@dataclass(frozen=True)
class OntologyVersion:
    knowledge_graph: str
    number: int
    content_hash: str
    origin: Origin
    created_at: datetime
    ontology: Ontology

    def to_yaml(self) -> str:
        return to_yaml(self.ontology)
