"""The self-hosted stetiq server: a FastAPI app exposing a `TrackingService` over HTTP.

The server holds no domain rules of its own: it wraps a `LocalTrackingService`
over a `SqlStore` (SQLite or Postgres) and translates JSON <-> entities with
`stetiq.tracking.wire`. Run it with `stetiq server --database-url ...`.
"""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Body, FastAPI, Request
from fastapi.responses import JSONResponse

from stetiq.errors import StetiqError
from stetiq.evaluation.answerability import CompetencyQuestionMapper
from stetiq.ontology import parse_dict
from stetiq.use_case import parse_use_case_dict
from stetiq.tracking import LocalTrackingService, SqlStore, TrackingService, wire

DATABASE_URL_ENV = "STETIQ_DATABASE_URL"
DEFAULT_DATABASE_URL = "sqlite:///.stetiq/server.db"


def create_app(
    database_url: str | None = None,
    *,
    service: TrackingService | None = None,
    question_mapper: CompetencyQuestionMapper | None = None,
) -> FastAPI:
    """Build the app over `service`, or over a `SqlStore` at `database_url`.

    `question_mapper` is the model structural answerability maps unmapped Competency
    Questions with (ticket #12); it only applies when `service` is not given."""
    if service is None:
        service = LocalTrackingService(
            SqlStore(database_url or DEFAULT_DATABASE_URL), question_mapper=question_mapper
        )
    tracking = service

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

    api = APIRouter(prefix=wire.API_PREFIX)

    @api.post("/knowledge-graphs", status_code=201)
    def create_knowledge_graph(
        name: str = Body(), declared_ontology: dict[str, Any] | None = Body(None)
    ) -> dict[str, Any]:
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

    @api.get("/observations/{observation_id}")
    def get_observation(observation_id: str) -> dict[str, Any]:
        return wire.observation_to_json(tracking.get_observation(observation_id))

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
    ) -> dict[str, Any]:
        evaluation = wire.evaluation_from_json({"metrics": metrics, "details": details})
        result = tracking.record_evaluation(
            name, "ontology_version", str(number), evaluator, evaluation
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
