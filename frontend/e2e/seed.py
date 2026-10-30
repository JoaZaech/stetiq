"""Seeds a tracking database for one Playwright test, through the Python SDK.

    uv run python frontend/e2e/seed.py SCENARIO TRACKING_URI

Each scenario is a function below that takes a local-mode `stetiq.Client` and returns
a JSON-serialisable dict (ids, version numbers, tokens...). It is printed on stdout
and handed to the test as `stetiq.seeded`. Add a scenario per data set a test needs,
and pick it in the spec with `test.use({ seed: 'name' })`.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Callable
from typing import Any

import stetiq

Scenario = Callable[[stetiq.Client], dict[str, Any]]


def empty(client: stetiq.Client) -> dict[str, Any]:
    """No Knowledge Graphs at all."""
    return {}


SCENARIOS: dict[str, Scenario] = {"empty": empty}


def main(scenario: str, tracking_uri: str) -> None:
    if scenario not in SCENARIOS:
        sys.exit(f"unknown seed scenario {scenario!r}; known: {', '.join(SCENARIOS)}")
    client = stetiq.Client(tracking_uri, graph_source=stetiq.InMemoryGraphSource())
    print(json.dumps(SCENARIOS[scenario](client)))


if __name__ == "__main__":
    main(*sys.argv[1:])
