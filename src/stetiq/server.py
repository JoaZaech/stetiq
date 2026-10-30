"""The self-hosted stetiq server: a FastAPI app exposing a `TrackingService` over HTTP.

The server holds no domain rules of its own: it wraps a `LocalTrackingService`
over a `SqlStore` (SQLite or Postgres) and translates JSON <-> entities with
`stetiq.tracking.wire`. Run it with `stetiq server --database-url ...`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

from fastapi import APIRouter, Body, Depends, FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from stetiq.auth import ALL_KNOWLEDGE_GRAPHS, ApiToken, Permission, TokenRegistry, bearer_token
from stetiq.errors import NotFoundError, PermissionDeniedError, StetiqError
from stetiq.evaluation.answerability import CompetencyQuestionMapper
from stetiq.evaluation.framework import SubjectKind
from stetiq.gates import parse_gates
from stetiq.ontology import parse_dict
from stetiq.tracking import LocalTrackingService, SqlStore, TrackingService, wire
from stetiq.tracking.entities import EvolutionMode
from stetiq.ui import FRONTEND_DIR, ui_router
from stetiq.use_case import parse_use_case_dict

DATABASE_URL_ENV = "STETIQ_DATABASE_URL"
DEFAULT_DATABASE_URL = "sqlite:///.stetiq/server.db"
CREATE_KG_PATH = wire.API_PREFIX + "/knowledge-graphs"
WHOAMI_PATH = wire.API_PREFIX + "/whoami"


class RecordedEvaluation(BaseModel):
    """An evaluation result computed client-side (a custom Evaluator, or executed
    Competency Questions for a run)."""

    evaluator: str
    metrics: dict[str, Any]
    details: list[dict[str, Any]] = []
    parameters: dict[str, Any] = {}
    use_case_version: int | None = None


def create_app(
    database_url: str | None = None,
    *,
    service: TrackingService | None = None,
    tokens: TokenRegistry | None = None,
    question_mapper: CompetencyQuestionMapper | None = None,
    frontend_dir: Path = FRONTEND_DIR,
    local_actor: str | None = None,
) -> FastAPI:
    """Build the app over `service`, or over a `SqlStore` at `database_url`.

    Every API request needs an API token from `tokens` (default: the registry in the
    same database). GET needs `read` on the targeted Knowledge Graph, anything else `edit`.

    With `local_actor` (`stetiq ui`), authentication is off: every request may edit every
    Knowledge Graph, and the audit log records `local_actor`.

    The built web UI in `frontend_dir` is served at `/ui`.

    `question_mapper` maps Competency Questions with neither a Concept mapping nor a
    query for structural answerability; it only applies when `service` is not given.
    """
    store = None
    if service is None:
        store = SqlStore(database_url or DEFAULT_DATABASE_URL)
        service = LocalTrackingService(store, question_mapper=question_mapper)
    if tokens is None and local_actor is None:
        tokens = TokenRegistry(store or SqlStore(database_url or DEFAULT_DATABASE_URL))
    tracking, registry = service, tokens
    local_token = ApiToken(
        id="local", user=local_actor or "", grants={ALL_KNOWLEDGE_GRAPHS: "edit"}
    )

    def authenticate(request: Request) -> ApiToken:
        if registry is None:  # local mode: whoever runs `stetiq ui` owns the database
            return local_token
        return registry.authenticate(bearer_token(request.headers.get("authorization")))

    def _target_knowledge_graph(token: ApiToken, path_params: dict[str, str]) -> str | None:
        """Which Knowledge Graph a request acts on, from its path parameters.

        A run or Observation the token cannot read answers exactly like an unknown one,
        so ids do not reveal what exists outside the token's grants."""
        if "name" in path_params:
            return path_params["name"]
        lookups = (
            ("run_id", tracking.get_run, "Construction Run {} does not exist"),
            ("observation_id", tracking.get_observation, "Observation {} does not exist"),
        )
        for param, lookup, missing in lookups:
            if param in path_params:
                entity_id = path_params[param]
                try:
                    kg = lookup(entity_id).knowledge_graph
                except NotFoundError:
                    kg = None
                if kg is None or not token.allows(kg, "read"):
                    raise NotFoundError(missing.format(repr(entity_id)))
                return kg
        return None

    def authorize(request: Request) -> None:
        token = authenticate(request)
        request.state.token = token
        needed: Permission = "read" if request.method in ("GET", "HEAD") else "edit"
        kg = _target_knowledge_graph(token, request.path_params)
        if kg is not None:
            token.require(kg, needed)
        elif (request.method, request.url.path) == ("GET", WHOAMI_PATH):
            pass  # who-am-I describes the token itself, not a Knowledge Graph
        elif not (request.method in ("POST", "GET") and request.url.path == CREATE_KG_PATH):
            # Fail closed: a route whose Knowledge Graph we cannot tell is not reachable.
            raise PermissionDeniedError(f"Cannot authorize {request.method} {request.url.path}")
        # POST /knowledge-graphs names its Knowledge Graph in the body: checked in the route.
        # GET /knowledge-graphs lists only the Knowledge Graphs the token can read.

    app = FastAPI(title="stetiq")

    @app.exception_handler(StetiqError)
    def _stetiq_error(_request: Request, exc: StetiqError) -> JSONResponse:
        status = next((s for cls, s in wire.ERROR_STATUS.items() if isinstance(exc, cls)), 400)
        return JSONResponse(wire.error_to_json(exc), status_code=status)

    @app.get("/health")
    def health() -> dict[str, bool]:
        return {"ok": True}

    api = APIRouter(prefix=wire.API_PREFIX, dependencies=[Depends(authorize)])

    @api.get("/whoami")
    def whoami(request: Request) -> dict[str, Any]:
        """Who the request acts as: the token's user and grants, or the local actor
        with edit on every Knowledge Graph under `stetiq ui`."""
        token: ApiToken = request.state.token
        mode = "local" if registry is None else "server"
        return {"mode": mode, "user": token.user, "grants": dict(token.grants)}

    @api.post("/knowledge-graphs", status_code=201)
    def create_knowledge_graph(
        request: Request,
        name: str = Body(),
        declared_ontology: dict[str, Any] | None = Body(None),
    ) -> dict[str, Any]:
        request.state.token.require(name, "edit")
        declared = None if declared_ontology is None else parse_dict(declared_ontology)
        return wire.knowledge_graph_to_json(tracking.create_knowledge_graph(name, declared))

    @api.get("/knowledge-graphs")
    def list_knowledge_graphs(request: Request) -> list[dict[str, Any]]:
        token = request.state.token
        return [
            wire.knowledge_graph_to_json(kg)
            for kg in tracking.list_knowledge_graphs()
            if token.allows(kg.name, "read")
        ]

    @api.get("/knowledge-graphs/{name}")
    def get_knowledge_graph(name: str) -> dict[str, Any]:
        return wire.knowledge_graph_to_json(tracking.get_knowledge_graph(name))

    @api.post("/knowledge-graphs/{name}/ontology-versions")
    def register_ontology(name: str, ontology: dict[str, Any] = Body(embed=True)) -> dict[str, Any]:
        # Always origin "registered": "run" versions only arise from ending a run.
        version = tracking.register_ontology(name, parse_dict(ontology))
        return wire.ontology_version_to_json(version)

    @api.get("/knowledge-graphs/{name}/ontology-versions")
    def list_ontology_versions(name: str) -> list[dict[str, Any]]:
        return [wire.ontology_version_to_json(v) for v in tracking.list_ontology_versions(name)]

    @api.get("/knowledge-graphs/{name}/ontology-versions/{number}")
    def get_ontology_version(name: str, number: int) -> dict[str, Any]:
        return wire.ontology_version_to_json(tracking.get_ontology_version(name, number))

    # --- Graph Sources -------------------------------------------------------------

    @api.put("/knowledge-graphs/{name}/graph-source")
    def bind_graph_source(name: str, scope: dict[str, Any] = Body(embed=True)) -> dict[str, Any]:
        bound = wire.graph_source_scope_from_json(scope)
        tracking.bind_graph_source(name, bound)
        return wire.graph_source_scope_to_json(bound)

    @api.get("/knowledge-graphs/{name}/graph-source")
    def get_graph_source(name: str) -> dict[str, Any]:
        return wire.graph_source_scope_to_json(tracking.get_graph_source(name))

    # --- Evolution Mode ---------------------------------------------------------------

    @api.put("/knowledge-graphs/{name}/evolution-mode")
    def set_evolution_mode(name: str, mode: str = Body(embed=True)) -> dict[str, str]:
        tracking.set_evolution_mode(name, cast(EvolutionMode, mode))  # validates the mode
        return {"mode": mode}

    @api.get("/knowledge-graphs/{name}/evolution-mode")
    def get_evolution_mode(name: str) -> dict[str, str]:
        return {"mode": tracking.get_evolution_mode(name)}

    # --- Construction Runs and Observations -------------------------------------------

    @api.post("/knowledge-graphs/{name}/runs", status_code=201)
    def start_run(name: str, ontology_version: int = Body(embed=True)) -> dict[str, Any]:
        return wire.run_to_json(tracking.start_run(name, ontology_version))

    @api.get("/knowledge-graphs/{name}/runs")
    def list_runs(name: str) -> list[dict[str, Any]]:
        return [wire.run_to_json(r) for r in tracking.list_runs(name)]

    @api.get("/runs/{run_id}")
    def get_run(run_id: str) -> dict[str, Any]:
        return wire.run_to_json(tracking.get_run(run_id))

    @api.post("/runs/{run_id}/params")
    def log_params(run_id: str, params: dict[str, str] = Body(embed=True)) -> dict[str, bool]:
        tracking.log_params(run_id, params)
        return {"ok": True}

    @api.post("/runs/{run_id}/metrics")
    def log_metrics(run_id: str, metrics: dict[str, float] = Body(embed=True)) -> dict[str, bool]:
        tracking.log_metrics(run_id, metrics)
        return {"ok": True}

    @api.post("/runs/{run_id}/end")
    def end_run(
        run_id: str, scope: dict[str, Any] = Body(), observed_schema: dict[str, Any] = Body()
    ) -> dict[str, Any]:
        observation = (
            wire.graph_source_scope_from_json(scope),
            wire.observed_schema_from_json(observed_schema),
        )
        return wire.run_to_json(tracking.end_run(run_id, observation))

    @api.post("/runs/{run_id}/fail")
    def fail_run(run_id: str) -> dict[str, Any]:
        return wire.run_to_json(tracking.fail_run(run_id))

    @api.get("/knowledge-graphs/{name}/observations")
    def list_observations(name: str) -> list[dict[str, Any]]:
        return [wire.observation_to_json(o) for o in tracking.list_observations(name)]

    @api.post("/knowledge-graphs/{name}/observations", status_code=201)
    def record_observation(
        name: str,
        scope: dict[str, Any] = Body(),
        observed_schema: dict[str, Any] = Body(),
        drift_thresholds: dict[str, Any] | None = Body(None),
    ) -> dict[str, Any]:
        observation = (
            wire.graph_source_scope_from_json(scope),
            wire.observed_schema_from_json(observed_schema),
        )
        thresholds = wire.drift_thresholds_from_json(drift_thresholds)
        return wire.observation_outcome_to_json(
            tracking.record_observation(name, observation, thresholds)
        )

    @api.get("/knowledge-graphs/{name}/drift-events")
    def list_drift_events(name: str) -> list[dict[str, Any]]:
        return [wire.drift_event_to_json(e) for e in tracking.list_drift_events(name)]

    @api.get("/observations/{observation_id}")
    def get_observation(observation_id: str) -> dict[str, Any]:
        return wire.observation_to_json(tracking.get_observation(observation_id))

    # --- Aliases and Promotion -----------------------------------------------------

    @api.put("/knowledge-graphs/{name}/aliases/{alias}")
    def set_alias(
        request: Request, name: str, alias: str, version: int = Body(), actor: str = Body()
    ) -> dict[str, Any]:
        # The audit log records the token's user; the actor the SDK sends is ignored.
        del actor
        user = request.state.token.user
        return wire.alias_to_json(tracking.set_alias(name, alias, version, user))

    @api.get("/knowledge-graphs/{name}/aliases/{alias}")
    def get_alias(name: str, alias: str) -> dict[str, Any]:
        return wire.alias_to_json(tracking.get_alias(name, alias))

    @api.get("/knowledge-graphs/{name}/aliases")
    def list_aliases(name: str) -> list[dict[str, Any]]:
        return [wire.alias_to_json(a) for a in tracking.list_aliases(name)]

    @api.get("/knowledge-graphs/{name}/promotions")
    def list_promotions(name: str) -> list[dict[str, Any]]:
        return [wire.promotion_to_json(p) for p in tracking.list_promotions(name)]

    @api.put("/knowledge-graphs/{name}/contract-alias")
    def set_contract_alias(name: str, alias: str = Body(embed=True)) -> dict[str, str]:
        tracking.set_contract_alias(name, alias)
        return {"alias": alias}

    @api.get("/knowledge-graphs/{name}/contract-alias")
    def get_contract_alias(name: str) -> dict[str, str]:
        return {"alias": tracking.get_contract_alias(name)}

    # --- Evaluation results ----------------------------------------------------------
    # One pair of routes per subject kind. Run results live under the run's Knowledge
    # Graph, whose subject check also confirms the run belongs to it.

    def results_of(name: str, kind: SubjectKind, subject_id: str) -> list[dict[str, Any]]:
        results = tracking.get_evaluation_results(name, kind, subject_id)
        return [wire.evaluation_result_to_json(r) for r in results]

    def record(
        name: str, kind: SubjectKind, subject_id: str, body: RecordedEvaluation
    ) -> dict[str, Any]:
        evaluation = wire.evaluation_from_json({"metrics": body.metrics, "details": body.details})
        result = tracking.record_evaluation(
            name,
            kind,
            subject_id,
            body.evaluator,
            evaluation,
            body.parameters,
            use_case_version=body.use_case_version,
        )
        return wire.evaluation_result_to_json(result)

    version_path = "/knowledge-graphs/{name}/ontology-versions/{number}"
    run_path = "/knowledge-graphs/{name}/runs/{run_id}"

    @api.get(version_path + "/evaluations")
    def get_version_evaluations(name: str, number: int) -> list[dict[str, Any]]:
        return results_of(name, "ontology_version", str(number))

    @api.post(version_path + "/evaluations", status_code=201)
    def record_version_evaluation(
        name: str, number: int, body: RecordedEvaluation
    ) -> dict[str, Any]:
        return record(name, "ontology_version", str(number), body)

    @api.get(run_path + "/evaluations")
    def get_run_evaluations(name: str, run_id: str) -> list[dict[str, Any]]:
        return results_of(name, "construction_run", run_id)

    @api.post(run_path + "/evaluations", status_code=201)
    def record_run_evaluation(name: str, run_id: str, body: RecordedEvaluation) -> dict[str, Any]:
        return record(name, "construction_run", run_id, body)

    @api.post(version_path + "/evaluate")
    def evaluate_version(
        name: str, number: int, use_case_version: int | None = Body(None, embed=True)
    ) -> list[dict[str, Any]]:
        results = tracking.evaluate_ontology_version(name, number, use_case_version)
        return [wire.evaluation_result_to_json(r) for r in results]

    @api.post("/runs/{run_id}/evaluate")
    def evaluate_run(run_id: str) -> list[dict[str, Any]]:
        results = tracking.evaluate_construction_run(run_id)
        return [wire.evaluation_result_to_json(r) for r in results]

    # --- Use Cases ------------------------------------------------------------------

    @api.post("/knowledge-graphs/{name}/use-case-versions")
    def register_use_case(name: str, use_case: dict[str, Any] = Body(embed=True)) -> dict[str, Any]:
        version = tracking.register_use_case(name, parse_use_case_dict(use_case))
        return wire.use_case_version_to_json(version)

    @api.get("/knowledge-graphs/{name}/use-case-versions")
    def list_use_case_versions(name: str) -> list[dict[str, Any]]:
        return [wire.use_case_version_to_json(v) for v in tracking.list_use_case_versions(name)]

    @api.get("/knowledge-graphs/{name}/use-case-versions/{number}")
    def get_use_case_version(name: str, number: int) -> dict[str, Any]:
        return wire.use_case_version_to_json(tracking.get_use_case_version(name, number))

    # --- Gates -----------------------------------------------------------------------

    @api.post("/knowledge-graphs/{name}/gate-results", status_code=201)
    def evaluate_gates(
        name: str,
        gates: list[dict[str, Any]] = Body(),
        version: int | None = Body(None),
        run: str | None = Body(None),
    ) -> dict[str, Any]:
        # The client sends Gate definitions only; the server computes every outcome.
        result = tracking.evaluate_gates(name, parse_gates(gates), version=version, run=run)
        return wire.gate_result_to_json(result)

    @api.get("/knowledge-graphs/{name}/gate-results")
    def list_gate_results(name: str) -> list[dict[str, Any]]:
        return [wire.gate_result_to_json(r) for r in tracking.list_gate_results(name)]

    app.include_router(api)
    app.include_router(ui_router(frontend_dir))
    return app
