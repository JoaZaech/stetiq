"""Observations and Drift."""

from __future__ import annotations

from datetime import date
from typing import Any

import stetiq
from stetiq.drift import DriftThresholds
from stetiq.graph_source import GraphSourceScope

from ._shared import SUPPORT_V1, Scenario, add_ada_and_ticket


def observed_support(_client: stetiq.Client) -> dict[str, Any]:
    """`support` observed twice: once at the end of a Construction Run (no Drift), then
    on demand after a `Refund` class, more Tickets (one with a `channel` attribute) and an
    `ESCALATED` relation appeared, which raises a Drift event against the Contract Alias
    (`production` -> v1)."""
    graph = stetiq.InMemoryGraphSource()
    client = stetiq.Client(_client.tracking_uri, graph_source=graph)
    client.create_knowledge_graph("support", ontology=SUPPORT_V1)
    client.bind_graph_source("support", GraphSourceScope(database="neo4j", label="Support"))
    ada, _ = add_ada_and_ticket(
        graph,
        ada_labels=("Support", "Party", "Customer"),
        ticket_labels=("Support", "Ticket"),
        priority=None,
    )
    with client.start_run("support", ontology_version=1) as run:
        pass
    for day in (2, 3):
        graph.add_node(["Support", "Ticket"], {"opened_at": date(2026, 1, day)})
    escalated = graph.add_node(
        ["Support", "Ticket"], {"opened_at": date(2026, 1, 4), "channel": "email"}
    )
    graph.add_relationship(ada, "ESCALATED", escalated)
    graph.add_node(["Support", "Refund"], {})
    outcome = client.observe("support", thresholds=DriftThresholds(max_count_increase=0.5))
    assert outcome.drift is not None
    return {"run_id": run.id, "observation_id": outcome.observation.id}


WORK_ORDERS = """
vocabularies:
  - {label: Status, values: [open, closed]}
node_types:
  - label: WorkOrder
    properties:
      - {name: status, type: STRING, vocabulary: Status}
      - {name: code, type: STRING, required: true}
"""


def observed_violation_rates(_client: stetiq.Client) -> dict[str, Any]:
    """`plant` observed twice on demand, with one listed value per Attribute
    (`value_cap=1`). The first Observation, the Baseline Observation, has every WorkOrder
    `code` set. In the second, half the WorkOrders lack their required `code` (a Violation
    Rate risen from 0% to 50%) and the most frequent `status` is `on_hold`, outside the
    Vocabulary, in a truncated value list, so its share is not comparable."""
    graph = stetiq.InMemoryGraphSource()
    client = stetiq.Client(_client.tracking_uri, graph_source=graph, value_cap=1)
    client.create_knowledge_graph("plant", ontology=WORK_ORDERS)
    for status in ("open", "open", "closed", "closed"):
        graph.add_node(["WorkOrder"], {"status": status, "code": "W"})
    for status, code in (("on_hold", "W"), ("on_hold", None), ("open", "W"), ("closed", None)):
        props = {"status": status} | ({"code": code} if code else {})
        graph.add_node(["WorkOrder"], props, database="later")
    client.bind_graph_source("plant", GraphSourceScope(database="neo4j"))
    baseline = client.observe("plant")
    client.bind_graph_source("plant", GraphSourceScope(database="later"))
    outcome = client.observe("plant")
    assert outcome.drift is not None and outcome.observation.not_comparable
    return {"baseline_id": baseline.observation.id, "observation_id": outcome.observation.id}


SCENARIOS: tuple[Scenario, ...] = (observed_support, observed_violation_rates)
