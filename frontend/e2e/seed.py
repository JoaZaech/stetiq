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
from stetiq.graph_source import GraphSourceScope

Scenario = Callable[[stetiq.Client], dict[str, Any]]


def empty(client: stetiq.Client) -> dict[str, Any]:
    """No Knowledge Graphs at all."""
    return {}


ONTOLOGY = """
node_types: [Customer, Ticket]
relationship_types: [OPENED]
patterns: [[Customer, OPENED, Ticket]]
"""


def knowledge_graphs(client: stetiq.Client) -> dict[str, Any]:
    """Two Knowledge Graphs: `support` (v2 registered, Contract Alias still on v1, a
    finished run) and `billing` (v1 only, a failed run)."""
    scope = GraphSourceScope(database="neo4j")
    client.create_knowledge_graph("support", ontology=ONTOLOGY)
    client.register_ontology("support", ONTOLOGY.replace("Ticket]", "Ticket, Agent]", 1))
    client.bind_graph_source("support", scope)
    client.start_run("support", ontology_version=1).end()
    client.create_knowledge_graph("billing", ontology=ONTOLOGY)
    client.bind_graph_source("billing", scope)
    client.start_run("billing", ontology_version=1).fail()
    return {}


SCENARIOS: dict[str, Scenario] = {"empty": empty, "knowledge_graphs": knowledge_graphs}


def main(scenario: str, tracking_uri: str) -> None:
    if scenario not in SCENARIOS:
        sys.exit(f"unknown seed scenario {scenario!r}; known: {', '.join(SCENARIOS)}")
    client = stetiq.Client(tracking_uri, graph_source=stetiq.InMemoryGraphSource())
    print(json.dumps(SCENARIOS[scenario](client)))


if __name__ == "__main__":
    main(*sys.argv[1:])
