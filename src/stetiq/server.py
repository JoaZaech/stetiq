"""The self-hosted stetiq server: a FastAPI app exposing a `TrackingService` over HTTP.

The server holds no domain rules of its own: it wraps a `LocalTrackingService`
over a `SqlStore` (SQLite or Postgres) and translates JSON <-> entities with
`stetiq.tracking.wire`. Run it with `stetiq server --database-url ...`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

from fastapi import APIRouter, Body, Depends, FastAPI, Request
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel

from stetiq.auth import (
    ALL_KNOWLEDGE_GRAPHS,
    CSRF_COOKIE,
    CSRF_HEADER,
    TOKEN_COOKIE,
    ApiToken,
    Permission,
    TokenRegistry,
    bearer_token,
    check_csrf,
    new_csrf_token,
)
from stetiq.errors import NotFoundError, PermissionDeniedError, StetiqError
from stetiq.evaluation.answerability import CompetencyQuestionMapper
from stetiq.evaluation.framework import SubjectKind
from stetiq.gates import parse_gates
from stetiq.ontology import parse_dict
from stetiq.ontology.diff import diff_ontologies
from stetiq.tracking import LocalTrackingService, SqlStore, TrackingService, codec, wire
from stetiq.tracking.entities import EvolutionMode
from stetiq.ui import FRONTEND_DIR, ui_router
from stetiq.use_case import parse_use_case_dict

DATABASE_URL_ENV = "STETIQ_DATABASE_URL"
DEFAULT_DATABASE_URL = "sqlite:///.stetiq/server.db"
CREATE_KG_PATH = wire.API_PREFIX + "/knowledge-graphs"
WHOAMI_PATH = wire.API_PREFIX + "/whoami"
SIGN_IN_PATH = "/auth/sign-in"
SIGN_OUT_PATH = "/auth/sign-out"


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
    # Local mode: whoever runs `stetiq ui` owns the database.
    local_token = (
        None
        if local_actor is None
        else ApiToken(id="local", user=local_actor, grants={ALL_KNOWLEDGE_GRAPHS: "edit"})
    )

    def authenticate(request: Request) -> ApiToken:
        if local_token is not None:
            return local_token
        assert registry is not None  # tokens are only left out in local mode
        bearer = bearer_token(request.headers.get("authorization"))
        if bearer is not None:
            return registry.authenticate(bearer)
        # The web UI's sign-in cookie. A browser sends it along with requests that other
        # sites trigger, so a write must also prove it comes from a page of ours.
        token = registry.authenticate(request.cookies.get(TOKEN_COOKIE))
        if request.method not in ("GET", "HEAD"):
            check_csrf(request.cookies.get(CSRF_COOKIE), request.headers.get(CSRF_HEADER))
        return token

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
        return JSONResponse(wire.error_to_json(exc), status_code=wire.error_status(exc))

    @app.get("/health")
    def health() -> dict[str, bool]:
        return {"ok": True}

    api = APIRouter(prefix=wire.API_PREFIX, dependencies=[Depends(authorize)])

    def describe(token: ApiToken) -> dict[str, Any]:
        return wire.whoami_to_json(token, local=local_token is not None)

    @api.get("/whoami")
    def whoami(request: Request) -> dict[str, Any]:
        """Who the request acts as: the token's user and grants, or the local actor
        with edit on every Knowledge Graph under `stetiq ui`."""
        return describe(request.state.token)

    # --- Web UI sign-in (ADR 0002: an existing token is pasted, never issued) ----------

    @app.post(SIGN_IN_PATH)
    def sign_in(
        request: Request, response: Response, token: str = Body(embed=True)
    ) -> dict[str, Any]:
        """Check a pasted API Token and keep it in an HttpOnly cookie for the web UI."""
        if registry is None or local_token is not None:
            raise StetiqError("stetiq ui runs without tokens: there is nothing to sign in to")
        signed_in = registry.authenticate(token)
        secure = request.url.scheme == "https"
        response.set_cookie(
            TOKEN_COOKIE, token, httponly=True, samesite="strict", path="/", secure=secure
        )
        # Not HttpOnly: the app echoes it in the CSRF header (double-submit).
        response.set_cookie(
            CSRF_COOKIE, new_csrf_token(), samesite="strict", path="/", secure=secure
        )
        return describe(signed_in)

    @app.post(SIGN_OUT_PATH, status_code=204)
    def sign_out(response: Response) -> None:
        """Make the browser forget the signed-in token (the token itself stays valid)."""
        for cookie in (TOKEN_COOKIE, CSRF_COOKIE):
            response.delete_cookie(cookie, path="/", samesite="strict")

    @api.post("/knowledge-graphs", status_code=201)
    def create_knowledge_graph(
        request: Request,
        name: str = Body(),
        declared_ontology: dict[str, Any] | None = Body(None),
    ) -> dict[str, Any]:
        request.state.token.require(name, "edit")
        declared = None if declared_ontology is None else parse_dict(declared_ontology)
        return codec.knowledge_graph_to_json(tracking.create_knowledge_graph(name, declared))

    @api.get("/knowledge-graphs")
    def list_knowledge_graphs(request: Request) -> list[dict[str, Any]]:
        token = request.state.token
        return [
            codec.knowledge_graph_summary_to_json(s)
            for s in tracking.list_knowledge_graphs()
            if token.allows(s.knowledge_graph.name, "read")
        ]

    @api.get("/knowledge-graphs/{name}")
    def get_knowledge_graph(name: str) -> dict[str, Any]:
        return codec.knowledge_graph_to_json(tracking.get_knowledge_graph(name))

    @api.put("/knowledge-graphs/{name}/description")
    def set_knowledge_graph_description(
        name: str, description: str | None = Body(embed=True)
    ) -> dict[str, Any]:
        kg = tracking.set_knowledge_graph_description(name, description)
        return codec.knowledge_graph_to_json(kg)

    @api.put("/knowledge-graphs/{name}/governance")
    def set_knowledge_graph_governance(
        name: str,
        steward: str | None = Body(default=None, embed=True),
        authority: str | None = Body(default=None, embed=True),
    ) -> dict[str, Any]:
        kg = tracking.set_knowledge_graph_governance(name, steward, authority)
        return codec.knowledge_graph_to_json(kg)

    @api.post("/knowledge-graphs/{name}/ontology-versions")
    def register_ontology(name: str, ontology: dict[str, Any] = Body(embed=True)) -> dict[str, Any]:
        # Always origin "registered": "run" versions only arise from ending a run.
        version = tracking.register_ontology(name, parse_dict(ontology))
        return codec.ontology_version_to_json(version)

    @api.get("/knowledge-graphs/{name}/ontology-versions")
    def list_ontology_versions(name: str) -> list[dict[str, Any]]:
        candidates = set(tracking.list_candidates(name))
        return [
            codec.ontology_version_to_json(v, candidate=v.number in candidates)
            for v in tracking.list_ontology_versions(name)
        ]

    @api.get("/knowledge-graphs/{name}/ontology-versions/{number}")
    def get_ontology_version(name: str, number: int) -> dict[str, Any]:
        return codec.ontology_version_to_json(tracking.get_ontology_version(name, number))

    @api.get("/knowledge-graphs/{name}/ontology-diff")
    def diff_ontology_versions(name: str, base: int, target: int) -> dict[str, Any]:
        # The same pure diff `Client.diff_ontology_versions` composes; no defaults here.
        return wire.ontology_diff_to_json(
            diff_ontologies(
                tracking.get_ontology_version(name, base).ontology,
                tracking.get_ontology_version(name, target).ontology,
            )
        )

    # --- Graph Sources -------------------------------------------------------------

    @api.put("/knowledge-graphs/{name}/graph-source")
    def bind_graph_source(name: str, scope: dict[str, Any] = Body(embed=True)) -> dict[str, Any]:
        bound = codec.graph_source_scope_from_json(scope)
        tracking.bind_graph_source(name, bound)
        return codec.graph_source_scope_to_json(bound)

    @api.get("/knowledge-graphs/{name}/graph-source")
    def get_graph_source(name: str) -> dict[str, Any]:
        return codec.graph_source_scope_to_json(tracking.get_graph_source(name))

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
    def start_run(
        name: str, ontology_version: int | None = Body(None), alias: str | None = Body(None)
    ) -> dict[str, Any]:
        # Older SDKs resolve the version themselves and send no alias.
        return codec.run_to_json(tracking.start_run(name, ontology_version, alias=alias))

    @api.get("/knowledge-graphs/{name}/runs")
    def list_runs(name: str) -> list[dict[str, Any]]:
        return [codec.run_to_json(r) for r in tracking.list_runs(name)]

    @api.get("/runs/{run_id}")
    def get_run(run_id: str) -> dict[str, Any]:
        return codec.run_to_json(tracking.get_run(run_id))

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
            codec.graph_source_scope_from_json(scope),
            codec.observed_schema_from_json(observed_schema),
        )
        return codec.run_to_json(tracking.end_run(run_id, observation))

    @api.post("/runs/{run_id}/fail")
    def fail_run(run_id: str) -> dict[str, Any]:
        return codec.run_to_json(tracking.fail_run(run_id))

    @api.get("/knowledge-graphs/{name}/observations")
    def list_observations(name: str) -> list[dict[str, Any]]:
        return [codec.observation_to_json(o) for o in tracking.list_observations(name)]

    @api.post("/knowledge-graphs/{name}/observations", status_code=201)
    def record_observation(
        name: str,
        scope: dict[str, Any] = Body(),
        observed_schema: dict[str, Any] = Body(),
        drift_thresholds: dict[str, Any] | None = Body(None),
    ) -> dict[str, Any]:
        observation = (
            codec.graph_source_scope_from_json(scope),
            codec.observed_schema_from_json(observed_schema),
        )
        thresholds = codec.requested_drift_thresholds_from_json(drift_thresholds)
        return codec.observation_outcome_to_json(
            tracking.record_observation(name, observation, thresholds)
        )

    @api.get("/knowledge-graphs/{name}/drift-events")
    def list_drift_events(name: str) -> list[dict[str, Any]]:
        return [codec.drift_event_to_json(e) for e in tracking.list_drift_events(name)]

    @api.get("/observations/{observation_id}")
    def get_observation(observation_id: str) -> dict[str, Any]:
        return codec.observation_to_json(tracking.get_observation(observation_id))

    # --- Aliases and Promotion -----------------------------------------------------

    @api.put("/knowledge-graphs/{name}/aliases/{alias}")
    def set_alias(
        request: Request,
        name: str,
        alias: str,
        version: int = Body(),
        actor: str | None = Body(None),
    ) -> dict[str, Any]:
        # The audit log records the token's user. Older SDKs still send an actor, which is
        # accepted for wire compatibility and ignored; the web UI sends none.
        del actor
        user = request.state.token.user
        return codec.alias_to_json(tracking.set_alias(name, alias, version, user))

    @api.get("/knowledge-graphs/{name}/aliases/{alias}")
    def get_alias(name: str, alias: str) -> dict[str, Any]:
        return codec.alias_to_json(tracking.get_alias(name, alias))

    @api.get("/knowledge-graphs/{name}/aliases")
    def list_aliases(name: str) -> list[dict[str, Any]]:
        return [codec.alias_to_json(a) for a in tracking.list_aliases(name)]

    @api.get("/knowledge-graphs/{name}/promotions")
    def list_promotions(name: str) -> list[dict[str, Any]]:
        return [codec.promotion_to_json(p) for p in tracking.list_promotions(name)]

    @api.put("/knowledge-graphs/{name}/contract-alias")
    def set_contract_alias(name: str, alias: str = Body(embed=True)) -> dict[str, str]:
        tracking.set_contract_alias(name, alias)
        return {"alias": alias}

    @api.get("/knowledge-graphs/{name}/contract-alias")
    def get_contract_alias(name: str) -> dict[str, str]:
        return {"alias": tracking.get_contract_alias(name)}

    @api.get("/knowledge-graphs/{name}/contract-version")
    def get_contract_version(name: str) -> dict[str, Any]:
        return codec.ontology_version_to_json(tracking.get_contract_version(name))

    # --- Evaluation results ----------------------------------------------------------
    # One pair of routes per subject kind. Run results live under the run's Knowledge
    # Graph, whose subject check also confirms the run belongs to it.

    def results_of(name: str, kind: SubjectKind, subject_id: str) -> list[dict[str, Any]]:
        results = tracking.get_evaluation_results(name, kind, subject_id)
        return [codec.evaluation_result_to_json(r) for r in results]

    def record(
        name: str, kind: SubjectKind, subject_id: str, body: RecordedEvaluation
    ) -> dict[str, Any]:
        evaluation = codec.evaluation_from_json({"metrics": body.metrics, "details": body.details})
        result = tracking.record_evaluation(
            name,
            kind,
            subject_id,
            body.evaluator,
            evaluation,
            body.parameters,
            use_case_version=body.use_case_version,
        )
        return codec.evaluation_result_to_json(result)

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

    @api.get("/knowledge-graphs/{name}/evaluations")
    def list_evaluations(name: str, subject_kind: str) -> list[dict[str, Any]]:
        # The service rejects an unknown subject kind with its own error.
        results = tracking.list_evaluation_results(name, cast(SubjectKind, subject_kind))
        return [codec.evaluation_result_to_json(r) for r in results]

    @api.post(version_path + "/evaluate")
    def evaluate_version(
        name: str, number: int, use_case_version: int | None = Body(None, embed=True)
    ) -> list[dict[str, Any]]:
        results = tracking.evaluate_ontology_version(name, number, use_case_version)
        return [codec.evaluation_result_to_json(r) for r in results]

    @api.post("/runs/{run_id}/evaluate")
    def evaluate_run(run_id: str) -> list[dict[str, Any]]:
        results = tracking.evaluate_construction_run(run_id)
        return [codec.evaluation_result_to_json(r) for r in results]

    # --- Use Cases ------------------------------------------------------------------

    @api.post("/knowledge-graphs/{name}/use-case-versions")
    def register_use_case(name: str, use_case: dict[str, Any] = Body(embed=True)) -> dict[str, Any]:
        version = tracking.register_use_case(name, parse_use_case_dict(use_case))
        return codec.use_case_version_to_json(version)

    @api.get("/knowledge-graphs/{name}/use-case-versions")
    def list_use_case_versions(name: str) -> list[dict[str, Any]]:
        return [codec.use_case_version_to_json(v) for v in tracking.list_use_case_versions(name)]

    @api.get("/knowledge-graphs/{name}/use-case-versions/latest")  # before {number}
    def get_latest_use_case_version(name: str) -> dict[str, Any]:
        return codec.use_case_version_to_json(tracking.get_use_case_version(name))

    @api.get("/knowledge-graphs/{name}/use-case-versions/{number}")
    def get_use_case_version(name: str, number: int) -> dict[str, Any]:
        return codec.use_case_version_to_json(tracking.get_use_case_version(name, number))

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
        return codec.gate_result_to_json(result)

    @api.get("/knowledge-graphs/{name}/gate-results")
    def list_gate_results(name: str) -> list[dict[str, Any]]:
        return [codec.gate_result_to_json(r) for r in tracking.list_gate_results(name)]

    app.include_router(api)
    app.include_router(ui_router(frontend_dir))
    return app
