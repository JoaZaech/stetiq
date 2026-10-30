"""The self-hosted stetiq server: a FastAPI app exposing a `TrackingService` over HTTP.

The server holds no domain rules of its own: it wraps a `LocalTrackingService`
over a `SqlStore` (SQLite or Postgres) and translates JSON <-> entities with
`stetiq.tracking.wire`. Run it with `stetiq server --database-url ...`.
"""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Body, Depends, FastAPI, Request
from fastapi.responses import JSONResponse

from stetiq.evaluation.answerability import CompetencyQuestionMapper
from stetiq.auth import Permission, TokenRegistry
from stetiq.errors import PermissionDeniedError, StetiqError
from stetiq.ontology import parse_dict
from stetiq.use_case import parse_use_case_dict
from stetiq.tracking import LocalTrackingService, SqlStore, TrackingService, wire

DATABASE_URL_ENV = "STETIQ_DATABASE_URL"
DEFAULT_DATABASE_URL = "sqlite:///.stetiq/server.db"
CREATE_KG_PATH = wire.API_PREFIX + "/knowledge-graphs"


def create_app(
    database_url: str | None = None,
    *,
    service: TrackingService | None = None,
    tokens: TokenRegistry | None = None,
    question_mapper: CompetencyQuestionMapper | None = None,
) -> FastAPI:
    """Build the app over `service`, or over a `SqlStore` at `database_url`.

    Every API request needs an API token from `tokens` (default: the registry in the
    same database). GET needs `read` on the targeted Knowledge Graph, anything else `edit`.

    `question_mapper` is the model structural answerability maps unmapped Competency
    Questions with (ticket #12); it only applies when `service` is not given.
    """
    if service is None or tokens is None:
        store = SqlStore(database_url or DEFAULT_DATABASE_URL)
        service = service or LocalTrackingService(store, question_mapper=question_mapper)
        tokens = tokens or TokenRegistry(store)
    tracking, registry = service, tokens

    def _target_knowledge_graph(path_params: dict[str, str]) -> str | None:
        """Which Knowledge Graph a request acts on, from its path parameters."""
        if "name" in path_params:
            return path_params["name"]
        if "run_id" in path_params:
            return tracking.get_run(path_params["run_id"]).knowledge_graph
        if "observation_id" in path_params:
            return tracking.get_observation(path_params["observation_id"]).knowledge_graph
        return None

    def authorize(request: Request) -> None:
        header = request.headers.get("authorization", "")
        scheme, _, value = header.partition(" ")
        token = registry.authenticate(value.strip() if scheme.lower() == "bearer" else None)
        request.state.token = token
        needed: Permission = "read" if request.method in ("GET", "HEAD") else "edit"
        kg = _target_knowledge_graph(request.path_params)
        if kg is not None:
            token.require(kg, needed)
        elif not (request.method == "POST" and request.url.path == CREATE_KG_PATH):
            # Fail closed: a route whose Knowledge Graph we cannot tell is not reachable.
            raise PermissionDeniedError(f"Cannot authorize {request.method} {request.url.path}")
        # POST /knowledge-graphs names its Knowledge Graph in the body: checked in the route.

    app = FastAPI(title="stetiq")

    @app.exception_handler(StetiqError)
    def _stetiq_error(_request: Request, exc: StetiqError) -> JSONResponse:
        status = next(
            (s for cls, s in wire.ERROR_STATUS.items() if isinstance(exc, cls)), 400
        )
        return JSONResponse(wire.error_to_json(exc), status_code=status)

    @app.get("/health")
    def health() -> dict[str, bool]:
        return {"ok": True}

    api = APIRouter(prefix=wire.API_PREFIX, dependencies=[Depends(authorize)])

    @api.post("/knowledge-graphs", status_code=201)
    def create_knowledge_graph(
        request: Request,
        name: str = Body(),
        declared_ontology: dict[str, Any] | None = Body(None),
    ) -> dict[str, Any]:
        request.state.token.require(name, "edit")
        declared = None if declared_ontology is None else parse_dict(declared_ontology)
        return wire.knowledge_graph_to_json(tracking.create_knowledge_graph(name, declared))

    @api.get("/knowledge-graphs/{name}")
    def get_knowledge_graph(name: str) -> dict[str, Any]:
        return wire.knowledge_graph_to_json(tracking.get_knowledge_graph(name))

    @api.post("/knowledge-graphs/{name}/ontology-versions")
    def register_ontology(
        name: str,
        ontology: dict[str, Any] = Body(),
        origin: Literal["registered", "run"] = Body("registered"),
    ) -> dict[str, Any]:
        version = tracking.register_ontology(name, parse_dict(ontology), origin)
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
        tracking.set_evolution_mode(name, mode)  # validates the mode
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
    # Evaluation results. Subject paths: ontology-versions/{number} here; Construction
    # Runs add runs/{id}/evaluations with run-level evaluation (ticket #13).
    version_path = "/knowledge-graphs/{name}/ontology-versions/{number}"

    @api.get(version_path + "/evaluations")
    def get_version_evaluations(name: str, number: int) -> list[dict[str, Any]]:
        results = tracking.get_evaluation_results(name, "ontology_version", str(number))
        return [wire.evaluation_result_to_json(r) for r in results]

    @api.post(version_path + "/evaluations", status_code=201)
    def record_version_evaluation(
        name: str,
        number: int,
        evaluator: str = Body(),
        metrics: dict[str, Any] = Body(),
        details: list[dict[str, Any]] = Body([]),
        parameters: dict[str, Any] = Body({}),
    ) -> dict[str, Any]:
        evaluation = wire.evaluation_from_json({"metrics": metrics, "details": details})
        result = tracking.record_evaluation(
            name, "ontology_version", str(number), evaluator, evaluation, parameters
        )
        return wire.evaluation_result_to_json(result)

    @api.post(version_path + "/evaluate")
    def evaluate_version(
        name: str, number: int, use_case_version: int | None = Body(None, embed=True)
    ) -> list[dict[str, Any]]:
        results = tracking.evaluate_ontology_version(name, number, use_case_version)
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

    app.include_router(api)
    return app
