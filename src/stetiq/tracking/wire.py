"""JSON wire format shared by the stetiq server and `RemoteTrackingService`.

Entities travel as plain JSON objects; Ontologies as their canonical dict form
(`ontology.to_dict`), which the server re-validates with `parse_dict`.
Errors travel as `{"error": {"type": <StetiqError subclass name>, "message": ...}}`
and are re-raised client-side as the same class, so both modes raise identically.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from stetiq import errors
from stetiq.conformance import Conformance
from stetiq.evaluation.framework import Detail, Evaluation
from stetiq.graph_source import GraphSourceScope, ObservedSchema
from stetiq.ontology import from_dict, to_dict
from stetiq.tracking.entities import (
    ConstructionRun,
    EvaluationResult,
    KnowledgeGraph,
    Observation,
    OntologyVersion,
)
from stetiq.tracking.entities import Alias, GateResult, Promotion
from stetiq.gates import outcome_from_dict, outcome_to_dict

API_PREFIX = "/api/v1"

# HTTP status per error class; anything unlisted is 400.
ERROR_STATUS: dict[type[errors.StetiqError], int] = {
    errors.NotFoundError: 404,
    errors.KnowledgeGraphAlreadyExistsError: 409,
    errors.OntologyValidationError: 422,
    errors.MissingDeclaredOntologyError: 422,
    errors.EvaluatorError: 422,
}


def knowledge_graph_to_json(kg: KnowledgeGraph) -> dict[str, Any]:
    return {"name": kg.name, "created_at": kg.created_at.isoformat()}


def knowledge_graph_from_json(d: dict[str, Any]) -> KnowledgeGraph:
    return KnowledgeGraph(name=d["name"], created_at=datetime.fromisoformat(d["created_at"]))


def ontology_version_to_json(v: OntologyVersion) -> dict[str, Any]:
    return {
        "knowledge_graph": v.knowledge_graph,
        "number": v.number,
        "content_hash": v.content_hash,
        "origin": v.origin,
        "created_at": v.created_at.isoformat(),
        "ontology": to_dict(v.ontology),
    }


def ontology_version_from_json(d: dict[str, Any]) -> OntologyVersion:
    return OntologyVersion(
        knowledge_graph=d["knowledge_graph"],
        number=d["number"],
        content_hash=d["content_hash"],
        origin=d["origin"],
        created_at=datetime.fromisoformat(d["created_at"]),
        ontology=from_dict(d["ontology"]),
    )


def _detail_to_json(d: Detail) -> dict[str, Any]:
    return {"item": d.item, "message": d.message, "metric": d.metric}


def _detail_from_json(d: dict[str, Any]) -> Detail:
    return Detail(item=d["item"], message=d.get("message", ""), metric=d.get("metric"))


def evaluation_to_json(e: Evaluation) -> dict[str, Any]:
    return {"metrics": dict(e.metrics), "details": [_detail_to_json(d) for d in e.details]}


def evaluation_from_json(d: dict[str, Any]) -> Evaluation:
    return Evaluation(
        metrics=dict(d["metrics"]),
        details=tuple(_detail_from_json(x) for x in d.get("details", [])),
    )


def evaluation_result_to_json(r: EvaluationResult) -> dict[str, Any]:
    return {
        "knowledge_graph": r.knowledge_graph,
        "subject_kind": r.subject_kind,
        "subject_id": r.subject_id,
        "evaluator": r.evaluator,
        "metrics": r.metrics,
        "details": [_detail_to_json(d) for d in r.details],
        "created_at": r.created_at.isoformat(),
        "parameters": dict(r.parameters),
    }


def evaluation_result_from_json(d: dict[str, Any]) -> EvaluationResult:
    return EvaluationResult(
        knowledge_graph=d["knowledge_graph"],
        subject_kind=d["subject_kind"],
        subject_id=d["subject_id"],
        evaluator=d["evaluator"],
        metrics=dict(d["metrics"]),
        details=tuple(_detail_from_json(x) for x in d["details"]),
        created_at=datetime.fromisoformat(d["created_at"]),
        parameters=dict(d.get("parameters", {})),
    )


def error_to_json(e: errors.StetiqError) -> dict[str, Any]:
    return {"error": {"type": type(e).__name__, "message": str(e)}}


def error_from_json(d: dict[str, Any]) -> errors.StetiqError:
    cls = getattr(errors, d["error"]["type"], None)
    if not (isinstance(cls, type) and issubclass(cls, errors.StetiqError)):
        cls = errors.StetiqError
    return cls(d["error"]["message"])


# --- Graph Sources, Construction Runs, Observations (ticket #4) -------------------------

ERROR_STATUS[errors.GraphSourceNotBoundError] = 409


def graph_source_scope_to_json(scope: GraphSourceScope) -> dict[str, Any]:
    return scope.to_dict()


def graph_source_scope_from_json(d: dict[str, Any]) -> GraphSourceScope:
    return GraphSourceScope.from_dict(d)


ERROR_STATUS[errors.RunNotActiveError] = 409


ERROR_STATUS[errors.InvalidEvolutionModeError] = 422


def _dt(value: str | None) -> datetime | None:
    return None if value is None else datetime.fromisoformat(value)


def run_to_json(run: ConstructionRun) -> dict[str, Any]:
    return {
        "id": run.id,
        "knowledge_graph": run.knowledge_graph,
        "ontology_version": run.ontology_version,
        "status": run.status,
        "started_at": run.started_at.isoformat(),
        "ended_at": None if run.ended_at is None else run.ended_at.isoformat(),
        "params": dict(run.params),
        "metrics": dict(run.metrics),
        "observation_id": run.observation_id,
        "conformance": None if run.conformance is None else run.conformance.to_dict(),
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
        conformance=None if d.get("conformance") is None else Conformance.from_dict(d["conformance"]),
        candidate_version=d.get("candidate_version"),
    )


def observed_schema_to_json(schema: ObservedSchema) -> dict[str, Any]:
    return schema.to_dict()


def observed_schema_from_json(d: dict[str, Any]) -> ObservedSchema:
    return ObservedSchema.from_dict(d)


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


# --- Aliases and Promotion (ticket #9) ---------------------------------------------------

ERROR_STATUS[errors.InvalidAliasNameError] = 422


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
        gate_result=d["gate_result"],
    )


# --- Gates (ticket #14) ------------------------------------------------------------------

ERROR_STATUS[errors.GateConfigError] = 422


def gate_result_to_json(r: GateResult) -> dict[str, Any]:
    return {
        "knowledge_graph": r.knowledge_graph,
        "subject_kind": r.subject_kind,
        "subject_id": r.subject_id,
        "ontology_version": r.ontology_version,
        "passed": r.passed,
        "outcomes": [outcome_to_dict(o) for o in r.outcomes],
        "evaluated_at": r.evaluated_at.isoformat(),
    }


def gate_result_from_json(d: dict[str, Any]) -> GateResult:
    return GateResult(
        knowledge_graph=d["knowledge_graph"],
        subject_kind=d["subject_kind"],
        subject_id=d["subject_id"],
        ontology_version=d["ontology_version"],
        outcomes=tuple(outcome_from_dict(o) for o in d["outcomes"]),
        evaluated_at=datetime.fromisoformat(d["evaluated_at"]),
    )
