"""Signing in with API Tokens (`mode: 'server'`)."""

from __future__ import annotations

from typing import Any

import stetiq

from ._shared import CUSTOMER_ONLY, Scenario, issue_token


def signed_in_users(client: stetiq.Client) -> dict[str, Any]:
    """`support` and `billing`, and a token for ada: edit on `support`, read on `billing`."""
    for kg in ("support", "billing"):
        client.create_knowledge_graph(kg, ontology=CUSTOMER_ONLY)
    return {"ada": issue_token(client, "ada", {"support": "edit", "billing": "read"})}


SCENARIOS: tuple[Scenario, ...] = (signed_in_users,)
