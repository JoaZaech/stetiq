"""HTTP transport for the stetiq server and `RemoteTrackingService`.

Entities travel in the JSON form `stetiq.tracking.codec` gives them; this module holds
what only the wire needs: the API prefix, who-am-I, the Ontology Diff and errors.
Errors travel as `{"error": {"type": <StetiqError subclass name>, "message": ...}}`
and are re-raised client-side as the same class, so both modes raise identically.
"""

from __future__ import annotations

from typing import Any

from stetiq import errors
from stetiq.auth import ApiToken
from stetiq.ontology.diff import OntologyDiff

API_PREFIX = "/api/v1"


def whoami_to_json(token: ApiToken, *, local: bool) -> dict[str, Any]:
    """Who a request acts as: `local` under `stetiq ui`, else a server API Token."""
    return {
        "mode": "local" if local else "server",
        "user": token.user,
        "grants": dict(token.grants),
    }


def ontology_diff_to_json(d: OntologyDiff) -> dict[str, Any]:
    """`classification` is the most severe change's, or None when nothing changed."""
    return {
        "classification": d.classification and str(d.classification),
        "changes": [
            {
                "concept": c.concept,
                "concept_kind": c.concept_kind,
                "kind": str(c.kind),
                "classification": str(c.classification),
                "detail": c.detail,
            }
            for c in d.changes
        ],
    }


# --- Errors ------------------------------------------------------------------------------

# HTTP status per error class. An error takes the status of its most specific class listed
# here (the first one in its MRO); anything else is 400.
ERROR_STATUS: dict[type[errors.StetiqError], int] = {
    errors.AuthenticationError: 401,
    errors.PermissionDeniedError: 403,
    errors.NotFoundError: 404,
    errors.KnowledgeGraphAlreadyExistsError: 409,
    errors.GraphSourceNotBoundError: 409,
    errors.RunNotActiveError: 409,
    errors.OntologyValidationError: 422,
    errors.MissingDeclaredOntologyError: 422,
    errors.EvaluatorError: 422,
    errors.InvalidEvolutionModeError: 422,
    errors.ConflictingArgumentsError: 422,
    errors.UseCaseValidationError: 422,
    errors.InvalidAliasNameError: 422,
    errors.InvalidDriftConfigError: 422,
    errors.GateConfigError: 422,
}


def error_status(e: errors.StetiqError) -> int:
    return next((ERROR_STATUS[c] for c in type(e).__mro__ if c in ERROR_STATUS), 400)


def error_to_json(e: errors.StetiqError) -> dict[str, Any]:
    return {"error": {"type": type(e).__name__, "message": str(e)}}


def error_from_json(d: dict[str, Any]) -> errors.StetiqError:
    """Every error class lives in `stetiq.errors` (tests/test_wire_errors.py checks it);
    an unknown name comes back as a plain `StetiqError`."""
    cls = getattr(errors, d["error"]["type"], None)
    if not (isinstance(cls, type) and issubclass(cls, errors.StetiqError)):
        cls = errors.StetiqError
    return cls(d["error"]["message"])
