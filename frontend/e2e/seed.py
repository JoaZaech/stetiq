"""Seeds a tracking database for one Playwright test, through the Python SDK.

    uv run python frontend/e2e/seed.py SCENARIO TRACKING_URI

The scenarios live in the `seeds` package, one module per feature area; its docstring
says where a new one goes. The scenario's result is printed on stdout as JSON.
"""

from __future__ import annotations

import json
import sys

import seeds

import stetiq


def main(name: str, tracking_uri: str) -> None:
    try:
        scenario = seeds.scenario(name)
    except seeds.UnknownScenario as error:
        sys.exit(str(error))
    client = stetiq.Client(tracking_uri, graph_source=stetiq.InMemoryGraphSource())
    print(json.dumps(scenario(client)))


if __name__ == "__main__":
    main(*sys.argv[1:])
