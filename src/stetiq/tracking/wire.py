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
from stetiq.ontology import from_dict, to_dict
from stetiq.tracking.entities import KnowledgeGraph, OntologyVersion

API_PREFIX = "/api/v1"

# HTTP status per error class; anything unlisted is 400.
ERROR_STATUS: dict[type[errors.StetiqError], int] = {
    errors.NotFoundError: 404,
    errors.KnowledgeGraphAlreadyExistsError: 409,
    errors.OntologyValidationError: 422,
    errors.MissingDeclaredOntologyError: 422,
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


def error_to_json(e: errors.StetiqError) -> dict[str, Any]:
    return {"error": {"type": type(e).__name__, "message": str(e)}}


def error_from_json(d: dict[str, Any]) -> errors.StetiqError:
    cls = getattr(errors, d["error"]["type"], None)
    if not (isinstance(cls, type) and issubclass(cls, errors.StetiqError)):
        cls = errors.StetiqError
    return cls(d["error"]["message"])
