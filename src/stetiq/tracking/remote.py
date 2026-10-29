"""Remote mode: a `TrackingService` that talks to a stetiq server over HTTP."""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

import httpx

from stetiq.errors import StetiqError
from stetiq.ontology import Ontology, to_dict
from stetiq.tracking import wire
from stetiq.tracking.entities import KnowledgeGraph, OntologyVersion, Origin


class RemoteTrackingService:
    """`base_url` is the server root, e.g. `http://localhost:5000`.

    `http` lets tests inject a client (e.g. FastAPI's `TestClient`, an `httpx.Client`).
    """

    def __init__(self, base_url: str, *, http: httpx.Client | None = None) -> None:
        self._base = base_url.rstrip("/") + wire.API_PREFIX
        self._http = http or httpx.Client(timeout=30.0)

    def _call(self, method: str, path: str, json: Any = None) -> Any:
        try:
            response = self._http.request(method, self._base + path, json=json)
        except httpx.HTTPError as e:
            raise StetiqError(f"Cannot reach stetiq server at {self._base}: {e}") from None
        if response.is_success:
            return response.json()
        try:
            body = response.json()
            error = wire.error_from_json(body)
        except (ValueError, KeyError, TypeError):
            error = StetiqError(f"stetiq server returned {response.status_code}: {response.text}")
        raise error

    @staticmethod
    def _kg_path(name: str) -> str:
        return f"/knowledge-graphs/{quote(name, safe='')}"

    def create_knowledge_graph(
        self, name: str, declared_ontology: Ontology | None
    ) -> KnowledgeGraph:
        body = {
            "name": name,
            "declared_ontology": None if declared_ontology is None else to_dict(declared_ontology),
        }
        return wire.knowledge_graph_from_json(self._call("POST", "/knowledge-graphs", body))

    def get_knowledge_graph(self, name: str) -> KnowledgeGraph:
        return wire.knowledge_graph_from_json(self._call("GET", self._kg_path(name)))

    def register_ontology(
        self, knowledge_graph: str, ontology: Ontology, origin: Origin = "registered"
    ) -> OntologyVersion:
        body = {"ontology": to_dict(ontology), "origin": origin}
        data = self._call("POST", self._kg_path(knowledge_graph) + "/ontology-versions", body)
        return wire.ontology_version_from_json(data)

    def list_ontology_versions(self, knowledge_graph: str) -> list[OntologyVersion]:
        data = self._call("GET", self._kg_path(knowledge_graph) + "/ontology-versions")
        return [wire.ontology_version_from_json(v) for v in data]

    def get_ontology_version(self, knowledge_graph: str, number: int) -> OntologyVersion:
        data = self._call("GET", f"{self._kg_path(knowledge_graph)}/ontology-versions/{number}")
        return wire.ontology_version_from_json(data)
