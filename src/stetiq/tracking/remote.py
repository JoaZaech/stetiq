"""Remote mode: a `TrackingService` that talks to a stetiq server over HTTP."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any
from urllib.parse import quote

import httpx

from stetiq import use_case as use_case_format
from stetiq.drift import DriftThresholds
from stetiq.errors import EvaluatorError, StetiqError
from stetiq.evaluation.framework import Evaluation, ParameterValue, SubjectKind
from stetiq.gates import Gate
from stetiq.graph_source import GraphSourceScope
from stetiq.ontology import Ontology, to_dict
from stetiq.tracking import wire
from stetiq.tracking.entities import (
    Alias,
    ConstructionRun,
    DriftEvent,
    EvaluationResult,
    EvolutionMode,
    GateResult,
    KnowledgeGraph,
    Observation,
    ObservationOutcome,
    OntologyVersion,
    Promotion,
    UseCaseVersion,
    validate_alias_name,
)
from stetiq.tracking.service import ObservationInput
from stetiq.use_case import UseCase


class RemoteTrackingService:
    """`base_url` is the server root, e.g. `http://localhost:5000`.

    `token` is the API token, sent as `Authorization: Bearer <token>`; the server requires one.
    `http` lets tests inject a client (e.g. FastAPI's `TestClient`, an `httpx.Client`).
    """

    def __init__(
        self, base_url: str, *, token: str | None = None, http: httpx.Client | None = None
    ) -> None:
        self._base = base_url.rstrip("/") + wire.API_PREFIX
        self._http = http or httpx.Client(timeout=30.0)
        self._headers = {"Authorization": f"Bearer {token}"} if token else {}

    def _call(self, method: str, path: str, json: Any = None) -> Any:
        try:
            response = self._http.request(
                method, self._base + path, json=json, headers=self._headers
            )
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

    def set_knowledge_graph_description(self, name: str, description: str | None) -> KnowledgeGraph:
        body = {"description": description}
        data = self._call("PUT", self._kg_path(name) + "/description", body)
        return wire.knowledge_graph_from_json(data)

    def list_knowledge_graphs(self) -> list[KnowledgeGraph]:
        return [wire.knowledge_graph_from_json(k) for k in self._call("GET", "/knowledge-graphs")]

    def register_ontology(self, knowledge_graph: str, ontology: Ontology) -> OntologyVersion:
        body = {"ontology": to_dict(ontology)}
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

    # --- Evolution Mode -----------------------------------------------------------------

    def set_evolution_mode(self, knowledge_graph: str, mode: EvolutionMode) -> None:
        self._call("PUT", self._kg_path(knowledge_graph) + "/evolution-mode", {"mode": mode})

    def get_evolution_mode(self, knowledge_graph: str) -> EvolutionMode:
        return self._call("GET", self._kg_path(knowledge_graph) + "/evolution-mode")["mode"]

    # --- Construction Runs and Observations -------------------------------------------

    @staticmethod
    def _run_path(run_id: str) -> str:
        return f"/runs/{quote(run_id, safe='')}"

    def start_run(self, knowledge_graph: str, ontology_version: int) -> ConstructionRun:
        body = {"ontology_version": ontology_version}
        return wire.run_from_json(
            self._call("POST", self._kg_path(knowledge_graph) + "/runs", body)
        )

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

    def record_observation(
        self,
        knowledge_graph: str,
        observation: ObservationInput,
        thresholds: DriftThresholds | None = None,
    ) -> ObservationOutcome:
        scope, schema = observation
        body = {
            "scope": wire.graph_source_scope_to_json(scope),
            "observed_schema": wire.observed_schema_to_json(schema),
            "drift_thresholds": wire.drift_thresholds_to_json(thresholds or DriftThresholds()),
        }
        data = self._call("POST", self._kg_path(knowledge_graph) + "/observations", body)
        return wire.observation_outcome_from_json(data)

    def list_drift_events(self, knowledge_graph: str) -> list[DriftEvent]:
        data = self._call("GET", self._kg_path(knowledge_graph) + "/drift-events")
        return [wire.drift_event_from_json(e) for e in data]

    # --- Aliases and Promotion ----------------------------------------------------------

    def _alias_path(self, knowledge_graph: str, name: str) -> str:
        return f"{self._kg_path(knowledge_graph)}/aliases/{quote(name, safe='')}"

    def set_alias(self, knowledge_graph: str, name: str, version: int, actor: str) -> Alias:
        validate_alias_name(name)  # a name like "a/b" would not even reach its route
        body = {"version": version, "actor": actor}
        return wire.alias_from_json(
            self._call("PUT", self._alias_path(knowledge_graph, name), body)
        )

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

    def _subject_path(
        self, knowledge_graph: str, subject_kind: SubjectKind, subject_id: str
    ) -> str:
        if subject_kind == "ontology_version":
            return (
                f"{self._kg_path(knowledge_graph)}/ontology-versions/{quote(subject_id, safe='')}"
            )
        if subject_kind == "construction_run":
            return f"{self._kg_path(knowledge_graph)}/runs/{quote(subject_id, safe='')}"
        raise EvaluatorError(f"Unsupported evaluation subject kind {subject_kind!r}")

    def evaluate_ontology_version(
        self, knowledge_graph: str, number: int, use_case_version: int | None = None
    ) -> list[EvaluationResult]:
        path = self._subject_path(knowledge_graph, "ontology_version", str(number))
        body = {"use_case_version": use_case_version}
        return [
            wire.evaluation_result_from_json(r)
            for r in self._call("POST", path + "/evaluate", body)
        ]

    def evaluate_construction_run(self, run_id: str) -> list[EvaluationResult]:
        return [
            wire.evaluation_result_from_json(r)
            for r in self._call("POST", self._run_path(run_id) + "/evaluate")
        ]

    def record_evaluation(
        self,
        knowledge_graph: str,
        subject_kind: SubjectKind,
        subject_id: str,
        evaluator: str,
        evaluation: Evaluation,
        parameters: Mapping[str, ParameterValue] | None = None,
        *,
        use_case_version: int | None = None,
    ) -> EvaluationResult:
        path = self._subject_path(knowledge_graph, subject_kind, subject_id) + "/evaluations"
        body = {
            "evaluator": evaluator,
            **wire.evaluation_to_json(evaluation),
            "parameters": dict(parameters or {}),
        }
        if use_case_version is not None:
            body["use_case_version"] = use_case_version
        return wire.evaluation_result_from_json(self._call("POST", path, body))

    def get_evaluation_results(
        self, knowledge_graph: str, subject_kind: SubjectKind, subject_id: str
    ) -> list[EvaluationResult]:
        path = self._subject_path(knowledge_graph, subject_kind, subject_id) + "/evaluations"
        return [wire.evaluation_result_from_json(r) for r in self._call("GET", path)]

    # --- Use Cases ------------------------------------------------------------------

    def register_use_case(self, knowledge_graph: str, use_case: UseCase) -> UseCaseVersion:
        body = {"use_case": use_case_format.to_dict(use_case_format.check_use_case(use_case))}
        data = self._call("POST", self._kg_path(knowledge_graph) + "/use-case-versions", body)
        return wire.use_case_version_from_json(data)

    def list_use_case_versions(self, knowledge_graph: str) -> list[UseCaseVersion]:
        data = self._call("GET", self._kg_path(knowledge_graph) + "/use-case-versions")
        return [wire.use_case_version_from_json(v) for v in data]

    def get_use_case_version(self, knowledge_graph: str, number: int) -> UseCaseVersion:
        data = self._call("GET", f"{self._kg_path(knowledge_graph)}/use-case-versions/{number}")
        return wire.use_case_version_from_json(data)

    # --- Gates --------------------------------------------------------------------------

    def evaluate_gates(
        self,
        knowledge_graph: str,
        gates: Sequence[Gate],
        *,
        version: int | None = None,
        run: str | None = None,
    ) -> GateResult:
        body = {"gates": [g.to_dict() for g in gates], "version": version, "run": run}
        data = self._call("POST", self._kg_path(knowledge_graph) + "/gate-results", body)
        return wire.gate_result_from_json(data)

    def list_gate_results(self, knowledge_graph: str) -> list[GateResult]:
        data = self._call("GET", self._kg_path(knowledge_graph) + "/gate-results")
        return [wire.gate_result_from_json(r) for r in data]
