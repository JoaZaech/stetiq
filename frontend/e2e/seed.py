"""Seeds a tracking database for one Playwright test, through the Python SDK.

    uv run python frontend/e2e/seed.py SCENARIO TRACKING_URI

Each scenario is a function below that takes a local-mode `stetiq.Client` and returns
a JSON-serialisable dict (ids, version numbers, tokens...). It is printed on stdout
and handed to the test as `stetiq.seeded`. Add a scenario per data set a test needs,
and pick it in the spec with `test.use({ seed: 'name' })`.

For a `mode: 'server'` test, issue API Tokens with `issue_token` and return them.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Callable
from typing import Any

import stetiq
from stetiq.auth import TokenRegistry

Scenario = Callable[[stetiq.Client], dict[str, Any]]


def issue_token(client: stetiq.Client, user: str, grants: dict[str, str]) -> dict[str, str]:
    """An API Token on the seeded database: `{"id", "value"}` (revoke it by `id`)."""
    token, value = TokenRegistry(client.tracking_uri).issue(user, grants)
    return {"id": token.id, "value": value}


def empty(client: stetiq.Client) -> dict[str, Any]:
    """No Knowledge Graphs at all."""
    return {}


def signed_in_users(client: stetiq.Client) -> dict[str, Any]:
    """`support` and `billing`, and a token for ada: edit on `support`, read on `billing`."""
    for kg in ("support", "billing"):
        client.create_knowledge_graph(kg, ontology="node_types:\n  - label: Customer\n")
    return {"ada": issue_token(client, "ada", {"support": "edit", "billing": "read"})}


SCENARIOS: dict[str, Scenario] = {"empty": empty, "signed_in_users": signed_in_users}


def main(scenario: str, tracking_uri: str) -> None:
    if scenario not in SCENARIOS:
        sys.exit(f"unknown seed scenario {scenario!r}; known: {', '.join(SCENARIOS)}")
    client = stetiq.Client(tracking_uri, graph_source=stetiq.InMemoryGraphSource())
    print(json.dumps(SCENARIOS[scenario](client)))


if __name__ == "__main__":
    main(*sys.argv[1:])
