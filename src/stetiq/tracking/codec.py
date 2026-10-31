"""The JSON form of every tracking entity, in both directions.

The one place an entity's JSON form is written: the HTTP wire (`server`,
`RemoteTrackingService`) and `SqlStore`'s JSON columns both use it.

Rules:
- A field added to an existing entity is read with `.get` and a default, so older
  payloads and older Store rows still parse.
- Ontologies and Use Cases travel in their canonical dict form (`ontology.to_dict`,
  `use_case.to_dict`); their hashing goes through `stetiq.digest`, not through here.
- The Ontology Diff is sent by `wire.ontology_diff_to_json`; it is a computed view, not stored.
- `encode`/`decode` dispatch on the entity type. `tests/test_codec.py` round-trips every
  dataclass in `stetiq.tracking.entities` through them, so a new entity needs an entry
  in `_CODECS`, and a new field that the codec drops fails that test.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from datetime import datetime
from typing import Any

from stetiq import use_case as use_case_format
from stetiq.conformance import Conformance
from stetiq.drift import DriftFinding, DriftThresholds
from stetiq.evaluation.framework import Detail, Evaluation
from stetiq.gates import GateOutcome, outcome_from_dict, outcome_to_dict
from stetiq.graph_source import GraphSourceScope, ObservedSchema
from stetiq.ontology import from_dict, to_dict
from stetiq.tracking.entities import (
    Alias,
    ConstructionRun,
    DriftEvent,
    EvaluationResult,
    GateResult,
    KnowledgeGraph,
    KnowledgeGraphSummary,
    Observation,
    ObservationOutcome,
    OntologyVersion,
    Promotion,
    UseCaseVersion,
)


def _dt(value: str | None) -> datetime | None:
    return None if value is None else datetime.fromisoformat(value)


def _iso(value: datetime | None) -> str | None:
    return None if value is None else value.isoformat()


# --- Knowledge Graphs and Ontology Versions ----------------------------------------------


def knowledge_graph_to_json(kg: KnowledgeGraph) -> dict[str, Any]:
    return {"name": kg.name, "created_at": kg.created_at.isoformat(), "description": kg.description}


def knowledge_graph_from_json(d: dict[str, Any]) -> KnowledgeGraph:
    # The description is optional: older servers do not send it.
    return KnowledgeGraph(
        name=d["name"],
        created_at=datetime.fromisoformat(d["created_at"]),
        description=d.get("description"),
    )


def knowledge_graph_summary_to_json(s: KnowledgeGraphSummary) -> dict[str, Any]:
    """A list item: the Knowledge Graph's own fields with the summary fields beside them."""
    return {
        **knowledge_graph_to_json(s.knowledge_graph),
        "contract_version": s.contract_version,
        "latest_version": s.latest_version,
        "last_run_status": s.last_run_status,
        "last_modified_at": _iso(s.last_modified_at),
    }


def knowledge_graph_summary_from_json(d: dict[str, Any]) -> KnowledgeGraphSummary:
    # The summary fields are optional: older servers do not send them.
    return KnowledgeGraphSummary(
        knowledge_graph=knowledge_graph_from_json(d),
        contract_version=d.get("contract_version"),
        latest_version=d.get("latest_version"),
        last_run_status=d.get("last_run_status"),
        last_modified_at=_dt(d.get("last_modified_at")),
    )


def ontology_version_to_json(
    v: OntologyVersion, *, candidate: bool | None = None
) -> dict[str, Any]:
    """`candidate` is only sent by the version list (older servers never send it)."""
    out = {
        "knowledge_graph": v.knowledge_graph,
        "number": v.number,
        "content_hash": v.content_hash,
        "origin": v.origin,
        "created_at": v.created_at.isoformat(),
        "ontology": to_dict(v.ontology),
    }
    if candidate is not None:
        out["candidate"] = candidate
    return out


def ontology_version_from_json(d: dict[str, Any]) -> OntologyVersion:
    return OntologyVersion(
        knowledge_graph=d["knowledge_graph"],
        number=d["number"],
        content_hash=d["content_hash"],
        origin=d["origin"],
        created_at=datetime.fromisoformat(d["created_at"]),
        ontology=from_dict(d["ontology"]),
    )


# --- Evaluations -------------------------------------------------------------------------


def detail_to_json(d: Detail) -> dict[str, Any]:
    out: dict[str, Any] = {"item": d.item, "message": d.message, "metric": d.metric}
    if d.data is not None:
        out["data"] = dict(d.data)
    return out


def detail_from_json(d: dict[str, Any]) -> Detail:
    return Detail(
        item=d["item"], message=d.get("message", ""), metric=d.get("metric"), data=d.get("data")
    )


def details_to_json(details: Iterable[Detail]) -> list[dict[str, Any]]:
    return [detail_to_json(d) for d in details]


def details_from_json(data: Iterable[dict[str, Any]]) -> tuple[Detail, ...]:
    return tuple(detail_from_json(d) for d in data)


def evaluation_to_json(e: Evaluation) -> dict[str, Any]:
    return {"metrics": dict(e.metrics), "details": details_to_json(e.details)}


def evaluation_from_json(d: dict[str, Any]) -> Evaluation:
    return Evaluation(metrics=dict(d["metrics"]), details=details_from_json(d.get("details", [])))


def evaluation_result_to_json(r: EvaluationResult) -> dict[str, Any]:
    return {
        "knowledge_graph": r.knowledge_graph,
        "subject_kind": r.subject_kind,
        "subject_id": r.subject_id,
        "evaluator": r.evaluator,
        "metrics": dict(r.metrics),
        "details": details_to_json(r.details),
        "created_at": r.created_at.isoformat(),
        "parameters": dict(r.parameters),
        "use_case_version": r.use_case_version,
    }


def evaluation_result_from_json(d: dict[str, Any]) -> EvaluationResult:
    return EvaluationResult(
        knowledge_graph=d["knowledge_graph"],
        subject_kind=d["subject_kind"],
        subject_id=d["subject_id"],
        evaluator=d["evaluator"],
        metrics=dict(d["metrics"]),
        details=details_from_json(d["details"]),
        created_at=datetime.fromisoformat(d["created_at"]),
        parameters=dict(d.get("parameters", {})),
        use_case_version=d.get("use_case_version"),
    )


# --- Graph Sources, Construction Runs, Observations -------------------------------------


def graph_source_scope_to_json(scope: GraphSourceScope) -> dict[str, Any]:
    return scope.to_dict()


def graph_source_scope_from_json(d: dict[str, Any]) -> GraphSourceScope:
    return GraphSourceScope.from_dict(d)


def observed_schema_to_json(schema: ObservedSchema) -> dict[str, Any]:
    return schema.to_dict()


def observed_schema_from_json(d: dict[str, Any]) -> ObservedSchema:
    return ObservedSchema.from_dict(d)


def conformance_to_json(c: Conformance) -> dict[str, Any]:
    return c.to_dict()


def conformance_from_json(d: dict[str, Any]) -> Conformance:
    return Conformance.from_dict(d)


def run_to_json(run: ConstructionRun) -> dict[str, Any]:
    return {
        "id": run.id,
        "knowledge_graph": run.knowledge_graph,
        "ontology_version": run.ontology_version,
        "status": run.status,
        "started_at": run.started_at.isoformat(),
        "ended_at": _iso(run.ended_at),
        "params": dict(run.params),
        "metrics": dict(run.metrics),
        "observation_id": run.observation_id,
        "conformance": None if run.conformance is None else conformance_to_json(run.conformance),
        "candidate_version": run.candidate_version,
    }


def run_from_json(d: dict[str, Any]) -> ConstructionRun:
    return ConstructionRun(
        id=d["id"],
        knowledge_graph=d["knowledge_graph"],
        ontology_version=d["ontology_version"],
        status=d["status"],
        started_at=datetime.fromisoformat(d["started_at"]),
        ended_at=_dt(d["ended_at"]),
        params=dict(d["params"]),
        metrics={k: float(v) for k, v in d["metrics"].items()},
        observation_id=d["observation_id"],
        conformance=None
        if d.get("conformance") is None
        else conformance_from_json(d["conformance"]),
        candidate_version=d.get("candidate_version"),
    )


def observation_to_json(obs: Observation) -> dict[str, Any]:
    return {
        "id": obs.id,
        "knowledge_graph": obs.knowledge_graph,
        "run_id": obs.run_id,
        "observed_at": obs.observed_at.isoformat(),
        "scope": graph_source_scope_to_json(obs.scope),
        "schema": observed_schema_to_json(obs.schema),
    }


def observation_from_json(d: dict[str, Any]) -> Observation:
    return Observation(
        id=d["id"],
        knowledge_graph=d["knowledge_graph"],
        run_id=d["run_id"],
        observed_at=datetime.fromisoformat(d["observed_at"]),
        scope=graph_source_scope_from_json(d["scope"]),
        schema=observed_schema_from_json(d["schema"]),
    )


# --- Use Cases ---------------------------------------------------------------------------


def use_case_version_to_json(v: UseCaseVersion) -> dict[str, Any]:
    return {
        "knowledge_graph": v.knowledge_graph,
        "number": v.number,
        "content_hash": v.content_hash,
        "created_at": v.created_at.isoformat(),
        "use_case": use_case_format.to_dict(v.use_case),
    }


def use_case_version_from_json(d: dict[str, Any]) -> UseCaseVersion:
    return UseCaseVersion(
        knowledge_graph=d["knowledge_graph"],
        number=d["number"],
        content_hash=d["content_hash"],
        created_at=datetime.fromisoformat(d["created_at"]),
        use_case=use_case_format.from_dict(d["use_case"]),
    )


# --- Aliases and Promotion ---------------------------------------------------------------


def alias_to_json(alias: Alias) -> dict[str, Any]:
    return {
        "knowledge_graph": alias.knowledge_graph,
        "name": alias.name,
        "version": alias.version,
        "updated_at": alias.updated_at.isoformat(),
    }


def alias_from_json(d: dict[str, Any]) -> Alias:
    return Alias(
        knowledge_graph=d["knowledge_graph"],
        name=d["name"],
        version=d["version"],
        updated_at=datetime.fromisoformat(d["updated_at"]),
    )


def promotion_to_json(p: Promotion) -> dict[str, Any]:
    return {
        "knowledge_graph": p.knowledge_graph,
        "alias": p.alias,
        "from_version": p.from_version,
        "to_version": p.to_version,
        "actor": p.actor,
        "promoted_at": p.promoted_at.isoformat(),
        "gate_result": p.gate_result,
    }


def promotion_from_json(d: dict[str, Any]) -> Promotion:
    return Promotion(
        knowledge_graph=d["knowledge_graph"],
        alias=d["alias"],
        from_version=d["from_version"],
        to_version=d["to_version"],
        actor=d["actor"],
        promoted_at=datetime.fromisoformat(d["promoted_at"]),
        gate_result=d.get("gate_result"),
    )


# --- Drift -------------------------------------------------------------------------------


def drift_thresholds_to_json(t: DriftThresholds) -> dict[str, Any]:
    return t.to_dict()


def requested_drift_thresholds_from_json(d: dict[str, Any] | None) -> DriftThresholds | None:
    """Thresholds a request asks for. None means "not given": the tracking service
    applies the default."""
    return None if d is None else DriftThresholds.from_dict(d)


def recorded_drift_thresholds_from_json(d: dict[str, Any] | None) -> DriftThresholds:
    """The thresholds a Drift event was judged with. None means none were recorded, so
    every check was off."""
    return DriftThresholds.from_dict(d or {})


def drift_findings_to_json(findings: Iterable[DriftFinding]) -> list[dict[str, Any]]:
    return [f.to_dict() for f in findings]


def drift_findings_from_json(data: Iterable[dict[str, Any]]) -> tuple[DriftFinding, ...]:
    return tuple(DriftFinding.from_dict(f) for f in data)


def drift_event_to_json(e: DriftEvent) -> dict[str, Any]:
    return {
        "id": e.id,
        "knowledge_graph": e.knowledge_graph,
        "observation_id": e.observation_id,
        "previous_observation_id": e.previous_observation_id,
        "contract_alias": e.contract_alias,
        "ontology_version": e.ontology_version,
        "detected_at": e.detected_at.isoformat(),
        "findings": drift_findings_to_json(e.findings),
        "thresholds": drift_thresholds_to_json(e.thresholds),
    }


def drift_event_from_json(d: dict[str, Any]) -> DriftEvent:
    return DriftEvent(
        id=d["id"],
        knowledge_graph=d["knowledge_graph"],
        observation_id=d["observation_id"],
        previous_observation_id=d["previous_observation_id"],
        contract_alias=d["contract_alias"],
        ontology_version=d["ontology_version"],
        detected_at=datetime.fromisoformat(d["detected_at"]),
        findings=drift_findings_from_json(d["findings"]),
        thresholds=recorded_drift_thresholds_from_json(d.get("thresholds")),
    )


def observation_outcome_to_json(o: ObservationOutcome) -> dict[str, Any]:
    return {
        "observation": observation_to_json(o.observation),
        "drift_event": None if o.drift is None else drift_event_to_json(o.drift),
    }


def observation_outcome_from_json(d: dict[str, Any]) -> ObservationOutcome:
    drift = d.get("drift_event")
    return ObservationOutcome(
        observation=observation_from_json(d["observation"]),
        drift=None if drift is None else drift_event_from_json(drift),
    )


# --- Gates -------------------------------------------------------------------------------


def gate_outcomes_to_json(outcomes: Iterable[GateOutcome]) -> list[dict[str, Any]]:
    return [outcome_to_dict(o) for o in outcomes]


def gate_outcomes_from_json(data: Iterable[dict[str, Any]]) -> tuple[GateOutcome, ...]:
    return tuple(outcome_from_dict(o) for o in data)


def gate_result_to_json(r: GateResult) -> dict[str, Any]:
    """`passed` is derived from the outcomes: sent for readers, ignored when decoding."""
    return {
        "knowledge_graph": r.knowledge_graph,
        "subject_kind": r.subject_kind,
        "subject_id": r.subject_id,
        "ontology_version": r.ontology_version,
        "passed": r.passed,
        "outcomes": gate_outcomes_to_json(r.outcomes),
        "evaluated_at": r.evaluated_at.isoformat(),
    }


def gate_result_from_json(d: dict[str, Any]) -> GateResult:
    return GateResult(
        knowledge_graph=d["knowledge_graph"],
        subject_kind=d["subject_kind"],
        subject_id=d["subject_id"],
        ontology_version=d["ontology_version"],
        outcomes=gate_outcomes_from_json(d["outcomes"]),
        evaluated_at=datetime.fromisoformat(d["evaluated_at"]),
    )


# --- Dispatch by type --------------------------------------------------------------------

_CODECS: dict[type, tuple[Callable[[Any], dict[str, Any]], Callable[[dict[str, Any]], Any]]] = {
    KnowledgeGraph: (knowledge_graph_to_json, knowledge_graph_from_json),
    KnowledgeGraphSummary: (knowledge_graph_summary_to_json, knowledge_graph_summary_from_json),
    OntologyVersion: (ontology_version_to_json, ontology_version_from_json),
    ConstructionRun: (run_to_json, run_from_json),
    Observation: (observation_to_json, observation_from_json),
    Alias: (alias_to_json, alias_from_json),
    Promotion: (promotion_to_json, promotion_from_json),
    EvaluationResult: (evaluation_result_to_json, evaluation_result_from_json),
    UseCaseVersion: (use_case_version_to_json, use_case_version_from_json),
    DriftEvent: (drift_event_to_json, drift_event_from_json),
    ObservationOutcome: (observation_outcome_to_json, observation_outcome_from_json),
    GateResult: (gate_result_to_json, gate_result_from_json),
    Detail: (detail_to_json, detail_from_json),
    Evaluation: (evaluation_to_json, evaluation_from_json),
}


def encode(value: Any) -> dict[str, Any]:
    """The JSON form of any entity this module covers."""
    return _CODECS[type(value)][0](value)


def decode[T](cls: type[T], data: dict[str, Any]) -> T:
    """The `cls` entity from its JSON form."""
    return _CODECS[cls][1](data)
