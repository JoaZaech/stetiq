"""Tracking entities returned by the SDK. Plain immutable values, no store handles."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

from stetiq.graph_source import GraphSourceScope, ObservedSchema
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


# "running" until ended; "finished" after a successful end (with its Observation);
# "failed" when the run crashed, was aborted, or its Observation could not be made.
RunStatus = Literal["running", "finished", "failed"]


@dataclass(frozen=True)
class ConstructionRun:
    id: str
    knowledge_graph: str
    ontology_version: int  # the Ontology Version consumed as Declared Ontology
    status: RunStatus
    started_at: datetime
    ended_at: datetime | None = None
    params: dict[str, str] = field(default_factory=dict)
    metrics: dict[str, float] = field(default_factory=dict)
    observation_id: str | None = None  # set when the run's ending Observation is stored


@dataclass(frozen=True)
class Observation:
    """A Graph Source's Observed Schema at one point in time: structure and aggregate
    statistics only, never instance data. `run_id` is None for on-demand Observations."""

    id: str
    knowledge_graph: str
    scope: GraphSourceScope
    observed_at: datetime
    schema: ObservedSchema
    run_id: str | None = None


@dataclass(frozen=True)
class RunComparison:
    """Runs side by side: `params[key][i]` / `metrics[key][i]` belong to `runs[i]`
    (None where that run did not log the key)."""

    runs: tuple[ConstructionRun, ...]
    params: dict[str, tuple[str | None, ...]]
    metrics: dict[str, tuple[float | None, ...]]

    @property
    def ontology_versions(self) -> tuple[int, ...]:
        return tuple(r.ontology_version for r in self.runs)
