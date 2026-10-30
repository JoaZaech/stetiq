"""Observations and Drift."""

from __future__ import annotations

from datetime import date
from typing import Any

import stetiq
from stetiq.drift import DriftThresholds
from stetiq.graph_source import GraphSourceScope

from ._shared import SUPPORT_V1, Scenario


def observed_support(_client: stetiq.Client) -> dict[str, Any]:
    """`support` observed twice: once at the end of a Construction Run (no Drift), then
    on demand after a `Refund` node type and more Tickets appeared, which raises a Drift
    event against the Contract Alias (`production` -> v1)."""
    graph = stetiq.InMemoryGraphSource()
    client = stetiq.Client(_client.tracking_uri, graph_source=graph)
    client.create_knowledge_graph("support", ontology=SUPPORT_V1)
    client.bind_graph_source("support", GraphSourceScope(database="neo4j", label="Support"))
    ada = graph.add_node(["Support", "Party", "Customer"], {"name": "Ada"})
    ticket = graph.add_node(["Support", "Ticket"], {"opened_at": date(2026, 1, 1)})
    graph.add_relationship(ada, "OPENED", ticket)
    with client.start_run("support", ontology_version=1) as run:
        pass
    for day in (2, 3, 4):
        graph.add_node(["Support", "Ticket"], {"opened_at": date(2026, 1, day)})
    graph.add_node(["Support", "Refund"], {})
    outcome = client.observe("support", thresholds=DriftThresholds(max_count_increase=0.5))
    assert outcome.drift is not None
    return {"run_id": run.id, "observation_id": outcome.observation.id}


SCENARIOS: tuple[Scenario, ...] = (observed_support,)
