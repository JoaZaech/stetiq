"""API-token authentication for server mode (local mode is tokenless).

An API token belongs to a user and grants `read` or `edit` permission per Knowledge
Graph (`edit` implies `read`; the Knowledge Graph `*` means every one). Tokens are
issued by an administrator against the server's database (`stetiq token create`);
the server stores only a SHA-256 hash of the secret, so a token is shown once.

A token reads `stq_<id>_<secret>`: `<id>` names it in listings and for revocation.
"""

from __future__ import annotations

import hashlib
import json
import secrets
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Literal, get_args

from sqlalchemy import insert, select, update

from stetiq.errors import AuthenticationError, NotFoundError, PermissionDeniedError, StetiqError
from stetiq.tracking.sql_store import SqlStore, api_tokens

Permission = Literal["read", "edit"]
PERMISSIONS: tuple[str, ...] = get_args(Permission)
ALL_KNOWLEDGE_GRAPHS = "*"
TOKEN_PREFIX = "stq"
# The web UI keeps a signed-in token in this HttpOnly cookie (ADR 0003). A write
# authenticated by it must echo the readable CSRF cookie in the CSRF header.
TOKEN_COOKIE = "stetiq_token"
CSRF_COOKIE = "stetiq_csrf"
CSRF_HEADER = "X-CSRF-Token"


@dataclass(frozen=True)
class ApiToken:
    """An issued token, without its secret."""

    id: str
    user: str
    grants: Mapping[str, Permission] = field(default_factory=dict)
    created_at: datetime | None = None
    revoked_at: datetime | None = None

    def permission_on(self, knowledge_graph: str) -> Permission | None:
        """The strongest permission granted on `knowledge_graph` (directly or via `*`)."""
        granted = {self.grants.get(knowledge_graph), self.grants.get(ALL_KNOWLEDGE_GRAPHS)}
        if "edit" in granted:
            return "edit"
        return "read" if "read" in granted else None

    def allows(self, knowledge_graph: str, needed: Permission) -> bool:
        have = self.permission_on(knowledge_graph)
        return have == "edit" or (have == "read" and needed == "read")

    def require(self, knowledge_graph: str, needed: Permission) -> None:
        if not self.allows(knowledge_graph, needed):
            raise PermissionDeniedError(
                f"Token {self.id} (user {self.user!r}) lacks {needed} permission "
                f"on Knowledge Graph {knowledge_graph!r}"
            )


def validate_grants(grants: Mapping[str, str]) -> dict[str, Permission]:
    if not grants:
        raise StetiqError("A token needs at least one grant (KNOWLEDGE_GRAPH=read|edit)")
    for kg, permission in grants.items():
        if not kg:
            raise StetiqError("A grant needs a Knowledge Graph name (or `*`)")
        if permission not in PERMISSIONS:
            raise StetiqError(f"Grant {kg}={permission}: permission must be read or edit")
    return dict(grants)  # type: ignore[arg-type]


def bearer_token(authorization: str | None) -> str | None:
    """The token value of an `Authorization: Bearer <token>` header, else None."""
    scheme, _, value = (authorization or "").partition(" ")
    return value.strip() or None if scheme.lower() == "bearer" else None


def new_csrf_token() -> str:
    return secrets.token_urlsafe(32)


def check_csrf(cookie: str | None, header: str | None) -> None:
    """Double-submit check: another site can make the browser send our cookies, but it
    cannot read the CSRF cookie to copy it into the header."""
    if not cookie or not header or not secrets.compare_digest(cookie.encode(), header.encode()):
        raise PermissionDeniedError(
            f"Missing or invalid CSRF token: send the {CSRF_COOKIE} cookie's value "
            f"in the {CSRF_HEADER} header"
        )


def _hash(secret: str) -> str:
    return hashlib.sha256(secret.encode()).hexdigest()


class TokenRegistry:
    """Issues, lists, revokes and checks API tokens in a server database."""

    def __init__(self, store: SqlStore | str) -> None:
        self._store = SqlStore(store) if isinstance(store, str) else store

    def issue(self, user: str, grants: Mapping[str, str]) -> tuple[ApiToken, str]:
        """Create a token; returns it and its full secret value (not retrievable later)."""
        if not user:
            raise StetiqError("A token needs a user")
        created_at = datetime.now(UTC)
        token = ApiToken(
            id=secrets.token_hex(4),
            user=user,
            grants=validate_grants(grants),
            created_at=created_at,
        )
        value = f"{TOKEN_PREFIX}_{token.id}_{secrets.token_urlsafe(32)}"
        with self._store._connection() as conn:
            conn.execute(
                insert(api_tokens).values(
                    id=token.id,
                    user=token.user,
                    secret_hash=_hash(value),
                    grants_json=json.dumps(token.grants, sort_keys=True),
                    created_at=created_at.isoformat(),
                    revoked_at=None,
                )
            )
        return token, value

    def authenticate(self, value: str | None) -> ApiToken:
        """The token `value` belongs to; AuthenticationError if missing, unknown or revoked."""
        if not value:
            raise AuthenticationError("This stetiq server requires an API token (set STETIQ_TOKEN)")
        with self._store._connection() as conn:
            row = conn.execute(
                select(api_tokens).where(api_tokens.c.secret_hash == _hash(value))
            ).first()
        if row is None or row.revoked_at is not None:
            raise AuthenticationError("Invalid or revoked API token")
        return _from_row(row)

    def list(self) -> list[ApiToken]:
        with self._store._connection() as conn:
            rows = conn.execute(select(api_tokens).order_by(api_tokens.c.created_at)).all()
        return [_from_row(r) for r in rows]

    def revoke(self, token_id: str) -> None:
        with self._store._connection() as conn:
            result = conn.execute(
                update(api_tokens)
                .where(api_tokens.c.id == token_id, api_tokens.c.revoked_at.is_(None))
                .values(revoked_at=datetime.now(UTC).isoformat())
            )
        if result.rowcount == 0:
            raise NotFoundError(f"No active API token {token_id!r}")


def _from_row(row) -> ApiToken:
    return ApiToken(
        id=row.id,
        user=row.user,
        grants=json.loads(row.grants_json),
        created_at=datetime.fromisoformat(row.created_at),
        revoked_at=None if row.revoked_at is None else datetime.fromisoformat(row.revoked_at),
    )
