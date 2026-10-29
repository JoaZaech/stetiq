"""Remote mode: a `TrackingService` that talks to a stetiq server over HTTP."""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

import httpx

from stetiq.errors import EvaluatorError, StetiqError
from stetiq.evaluation.framework import Evaluation, SubjectKind
from stetiq.graph_source import GraphSourceScope
from stetiq.ontology import Ontology, to_dict
from stetiq.tracking import wire
from stetiq.tracking.entities import (
    Alias,
    Promotion,
    validate_alias_name,
    ConstructionRun,
    EvaluationResult,
    KnowledgeGraph,
    Observation,
    OntologyVersion,
    Origin,
)
from stetiq.tracking.service import ObservationInput


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

    # --- Graph Sources ------------------------------------------------------------------

    def bind_graph_source(self, knowledge_graph: str, scope: GraphSourceScope) -> None:
        body = {"scope": wire.graph_source_scope_to_json(scope)}
        self._call("PUT", self._kg_path(knowledge_graph) + "/graph-source", body)

    def get_graph_source(self, knowledge_graph: str) -> GraphSourceScope:
        data = self._call("GET", self._kg_path(knowledge_graph) + "/graph-source")
        return wire.graph_source_scope_from_json(data)

    # --- Construction Runs and Observations -------------------------------------------

    @staticmethod
    def _run_path(run_id: str) -> str:
        return f"/runs/{quote(run_id, safe='')}"

    def start_run(self, knowledge_graph: str, ontology_version: int) -> ConstructionRun:
        body = {"ontology_version": ontology_version}
        return wire.run_from_json(self._call("POST", self._kg_path(knowledge_graph) + "/runs", body))

    def get_run(self, run_id: str) -> ConstructionRun:
        return wire.run_from_json(self._call("GET", self._run_path(run_id)))

    def list_runs(self, knowledge_graph: str) -> list[ConstructionRun]:
        data = self._call("GET", self._kg_path(knowledge_graph) + "/runs")
        return [wire.run_from_json(r) for r in data]

    def log_params(self, run_id: str, params: dict[str, str]) -> None:
        self._call("POST", self._run_path(run_id) + "/params", {"params": params})

    def log_metrics(self, run_id: str, metrics: dict[str, float]) -> None:
        self._call("POST", self._run_path(run_id) + "/metrics", {"metrics": metrics})

    def end_run(self, run_id: str, observation: ObservationInput) -> ConstructionRun:
        scope, schema = observation
        body = {
            "scope": wire.graph_source_scope_to_json(scope),
            "observed_schema": wire.observed_schema_to_json(schema),
        }
        return wire.run_from_json(self._call("POST", self._run_path(run_id) + "/end", body))

    def fail_run(self, run_id: str) -> ConstructionRun:
        return wire.run_from_json(self._call("POST", self._run_path(run_id) + "/fail"))

    def get_observation(self, observation_id: str) -> Observation:
        data = self._call("GET", f"/observations/{quote(observation_id, safe='')}")
        return wire.observation_from_json(data)

    def list_observations(self, knowledge_graph: str) -> list[Observation]:
        data = self._call("GET", self._kg_path(knowledge_graph) + "/observations")
        return [wire.observation_from_json(o) for o in data]

    # --- Aliases and Promotion ----------------------------------------------------------

    def _alias_path(self, knowledge_graph: str, name: str) -> str:
        return f"{self._kg_path(knowledge_graph)}/aliases/{quote(name, safe='')}"

    def set_alias(self, knowledge_graph: str, name: str, version: int, actor: str) -> Alias:
        validate_alias_name(name)  # a name like "a/b" would not even reach its route
        body = {"version": version, "actor": actor}
        return wire.alias_from_json(self._call("PUT", self._alias_path(knowledge_graph, name), body))

    def get_alias(self, knowledge_graph: str, name: str) -> Alias:
        return wire.alias_from_json(self._call("GET", self._alias_path(knowledge_graph, name)))

    def list_aliases(self, knowledge_graph: str) -> list[Alias]:
        data = self._call("GET", self._kg_path(knowledge_graph) + "/aliases")
        return [wire.alias_from_json(a) for a in data]

    def list_promotions(self, knowledge_graph: str) -> list[Promotion]:
        data = self._call("GET", self._kg_path(knowledge_graph) + "/promotions")
        return [wire.promotion_from_json(p) for p in data]

    def set_contract_alias(self, knowledge_graph: str, alias: str) -> None:
        self._call("PUT", self._kg_path(knowledge_graph) + "/contract-alias", {"alias": alias})

    def get_contract_alias(self, knowledge_graph: str) -> str:
        return self._call("GET", self._kg_path(knowledge_graph) + "/contract-alias")["alias"]

    def _subject_path(self, knowledge_graph: str, subject_kind: SubjectKind, subject_id: str) -> str:
        if subject_kind == "ontology_version":
            return f"{self._kg_path(knowledge_graph)}/ontology-versions/{quote(subject_id, safe='')}"
        raise EvaluatorError(f"Unsupported evaluation subject kind {subject_kind!r}")

    def evaluate_ontology_version(
        self, knowledge_graph: str, number: int
    ) -> list[EvaluationResult]:
        path = self._subject_path(knowledge_graph, "ontology_version", str(number))
        return [wire.evaluation_result_from_json(r) for r in self._call("POST", path + "/evaluate")]

    def record_evaluation(
        self,
        knowledge_graph: str,
        subject_kind: SubjectKind,
        subject_id: str,
        evaluator: str,
        evaluation: Evaluation,
    ) -> EvaluationResult:
        path = self._subject_path(knowledge_graph, subject_kind, subject_id) + "/evaluations"
        body = {"evaluator": evaluator, **wire.evaluation_to_json(evaluation)}
        return wire.evaluation_result_from_json(self._call("POST", path, body))

    def get_evaluation_results(
        self, knowledge_graph: str, subject_kind: SubjectKind, subject_id: str
    ) -> list[EvaluationResult]:
        path = self._subject_path(knowledge_graph, subject_kind, subject_id) + "/evaluations"
        return [wire.evaluation_result_from_json(r) for r in self._call("GET", path)]
