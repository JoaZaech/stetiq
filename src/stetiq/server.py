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
from stetiq.ontology import parse_dict
from stetiq.tracking import LocalTrackingService, SqlStore, TrackingService, wire

DATABASE_URL_ENV = "STETIQ_DATABASE_URL"
DEFAULT_DATABASE_URL = "sqlite:///.stetiq/server.db"


def create_app(
    database_url: str | None = None, *, service: TrackingService | None = None
) -> FastAPI:
    """Build the app over `service`, or over a `SqlStore` at `database_url`."""
    if service is None:
        service = LocalTrackingService(SqlStore(database_url or DEFAULT_DATABASE_URL))
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
    def evaluate_version(name: str, number: int) -> list[dict[str, Any]]:
        results = tracking.evaluate_ontology_version(name, number)
        return [wire.evaluation_result_to_json(r) for r in results]

    app.include_router(api)
    return app
