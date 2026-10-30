"""Tracking entities returned by the SDK. Plain immutable values, no store handles."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

from stetiq.conformance import Conformance
from stetiq.drift import DriftFinding, DriftThresholds
from stetiq.errors import InvalidAliasNameError
from stetiq.evaluation.framework import Detail, MetricValue, ParameterValue, SubjectKind
from stetiq.gates import Gate, GateOutcome
from stetiq.graph_source import GraphSourceScope, ObservedSchema
from stetiq.ontology import Ontology, to_yaml
from stetiq.use_case import UseCase

# "registered": registered by hand; "run": created as a Candidate by a Construction Run (later ticket).
Origin = Literal["registered", "run"]


@dataclass(frozen=True)
class KnowledgeGraph:
    """A Knowledge Graph. The summary fields are filled in only when Knowledge Graphs
    are listed, so a list can show each one's state at a glance; elsewhere they are None.

    `contract_version` is the version the Contract Alias points to, `latest_version` the
    newest Ontology Version, `last_run_status` the status of the most recently started
    Construction Run (None without runs) and `last_modified_at` the time of its latest
    recorded change (version, run, Promotion, Use Case Version or Observation)."""

    name: str
    created_at: datetime
    contract_version: int | None = None
    latest_version: int | None = None
    last_run_status: RunStatus | None = None
    last_modified_at: datetime | None = None


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

# A Knowledge Graph's setting for runs that introduce new Concepts: "strict" fails the
# run, "evolving" (the default) creates a Candidate Ontology Version.
EvolutionMode = Literal["strict", "evolving"]
DEFAULT_EVOLUTION_MODE: EvolutionMode = "evolving"


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
    # Conformance of the ending Observation to the Declared Ontology (None until ended
    # with an Observation).
    conformance: Conformance | None = None
    # The Candidate Ontology Version this run gave rise to (evolving mode, new Concepts).
    candidate_version: int | None = None


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
    (None where that run did not log the key).

    `conformance[i]` is `runs[i]`'s Conformance (None without an Observation).
    `evaluations["<evaluator>.<metric>"][i]` is the metric of `runs[i]`'s latest
    run-level Evaluator result; an Evaluator run with parameters is keyed
    `"<evaluator>[k=v,...].<metric>"`."""

    runs: tuple[ConstructionRun, ...]
    params: dict[str, tuple[str | None, ...]]
    metrics: dict[str, tuple[float | None, ...]]
    conformance: tuple[Conformance | None, ...] = ()
    evaluations: dict[str, tuple[float | None, ...]] = field(default_factory=dict)

    @property
    def ontology_versions(self) -> tuple[int, ...]:
        return tuple(r.ontology_version for r in self.runs)


# --- Aliases and Promotion ---------------------------------------------------------------

DEFAULT_CONTRACT_ALIAS = "production"
_ALIAS_NAME = re.compile(r"[A-Za-z0-9_.-]+")


def validate_alias_name(name: str) -> None:
    """Alias names are URL-path safe: letters, digits, `_`, `-`, `.`."""
    if not _ALIAS_NAME.fullmatch(name):
        raise InvalidAliasNameError(f"Alias name {name!r} must be letters, digits, '_', '-' or '.'")


@dataclass(frozen=True)
class Alias:
    """A named, movable pointer to one Ontology Version of a Knowledge Graph."""

    knowledge_graph: str
    name: str
    version: int
    updated_at: datetime


@dataclass(frozen=True)
class Promotion:
    """One audit-log entry: an Alias moved (or created, `from_version` None) by `actor`.

    `gate_result` is the target version's latest Gate result at the time of the move;
    it stays None until Gates exist."""

    knowledge_graph: str
    alias: str
    from_version: int | None
    to_version: int
    actor: str
    promoted_at: datetime
    gate_result: str | None = None


@dataclass(frozen=True)
class EvaluationResult:
    """One Evaluator's stored result against one subject.

    The subject is (`knowledge_graph`, `subject_kind`, `subject_id`): `subject_id`
    is the version number (as text) for an Ontology Version, the run id for a
    Construction Run.
    """

    knowledge_graph: str
    subject_kind: SubjectKind
    subject_id: str
    evaluator: str
    metrics: dict[str, MetricValue]
    details: tuple[Detail, ...]
    created_at: datetime
    # The Evaluator's configuration (e.g. its reference Ontology Version); {} if none.
    parameters: dict[str, ParameterValue] = field(default_factory=dict)
    # The Use Case version the Evaluator judged against (structural answerability);
    # None for Evaluators that use no Use Case.
    use_case_version: int | None = None


@dataclass(frozen=True)
class UseCaseVersion:
    """An immutable snapshot of a Knowledge Graph's Use Case (its Competency Questions),
    numbered independently of Ontology Versions. `use_case` is in canonical order
    (questions sorted by id)."""

    knowledge_graph: str
    number: int
    content_hash: str
    created_at: datetime
    use_case: UseCase


# --- Drift -------------------------------------------------------------------------------


@dataclass(frozen=True)
class DriftEvent:
    """An alert raised by an on-demand Observation that diverged from the contract (or,
    beyond `thresholds`, from the previous Observation). Never an Ontology Version.

    `contract_alias` / `ontology_version` are the contract the Observation was compared
    with at the time; `thresholds` are the statistical thresholds used."""

    id: str
    knowledge_graph: str
    observation_id: str
    previous_observation_id: str | None
    contract_alias: str
    ontology_version: int
    detected_at: datetime
    findings: tuple[DriftFinding, ...]
    thresholds: DriftThresholds = field(default_factory=DriftThresholds)

    @property
    def structural(self) -> tuple[DriftFinding, ...]:
        return tuple(f for f in self.findings if f.structural)

    @property
    def statistical(self) -> tuple[DriftFinding, ...]:
        return tuple(f for f in self.findings if not f.structural)


@dataclass(frozen=True)
class ObservationOutcome:
    """What an on-demand Observation produced: the Observation, and its Drift event if any."""

    observation: Observation
    drift: DriftEvent | None = None

    @property
    def drifted(self) -> bool:
        return self.drift is not None


# --- Gates ---------------------------------------------------------------------------


@dataclass(frozen=True)
class GateResult:
    """One recorded Gate evaluation: each Gate's outcome together with the Gate
    definition used (`outcome.gate`).

    `ontology_version` is the version the subject stands for: the version itself, or
    for a run its Candidate if it gave rise to one, else the version it consumed.
    Promotion audit entries take the target version's latest `GateResult`."""

    knowledge_graph: str
    subject_kind: SubjectKind  # an Ontology Version (e.g. a Candidate) or a run
    subject_id: str
    ontology_version: int
    outcomes: tuple[GateOutcome, ...]
    evaluated_at: datetime

    @property
    def passed(self) -> bool:
        return all(o.passed for o in self.outcomes)

    @property
    def failed(self) -> tuple[GateOutcome, ...]:
        return tuple(o for o in self.outcomes if not o.passed)

    @property
    def gates(self) -> tuple[Gate, ...]:
        return tuple(o.gate for o in self.outcomes)
