"""Consumer Gates declared in the Use Case, and their recorded verdicts."""

from __future__ import annotations

from typing import Any

import stetiq
from stetiq.graph_source import GraphSourceScope

from ._shared import Scenario

PLANT_ONTOLOGY = """
node_types:
  - label: Machine
  - label: WorkOrder
relationship_types:
  - label: PERFORMED_ON
patterns:
  - [WorkOrder, PERFORMED_ON, Machine]
"""

TECHNICIANS = "MATCH (w:WorkOrder {kind: 'breakdown'}) RETURN w"
MACHINES = "MATCH (m:Machine) RETURN m"

PLANT_USE_CASE = f"""
competency_questions:
  - id: breakdown-technicians
    question: Which technicians fixed breakdowns?
    query: "{TECHNICIANS}"
  - id: machines
    question: Which machines are there?
    query: "{MACHINES}"
consumers:
  - id: reliability-dashboard
    name: Reliability dashboard
    kind: dashboard
    tasks:
      - id: triage-breakdowns
        description: Triage breakdowns
        competency_questions: [breakdown-technicians]
    consumer_gates:
      - name: triage-rows-hold
        check: row_count_drop
        task: triage-breakdowns
        max_drop: 0.10
  - id: maintenance-assistant
    name: Maintenance assistant
    kind: agent
    tasks:
      - id: list-machines
        description: List the machines
        competency_questions: [machines]
    consumer_gates:
      - check: row_count_drop
        task: list-machines
        max_drop: 0.5
  - id: safety-team
    name: Safety team
    tasks:
      - id: audit-machines
        description: Audit the machines
        competency_questions: [machines]
    consumer_gates:
      - check: row_count_drop
        task: audit-machines
        max_drop: 0
  - id: planning-team
    name: Planning team
    tasks:
      - id: plan-maintenance
        description: Plan maintenance
        competency_questions: [machines]
"""


def _run(client: stetiq.Client, *, technicians: int, machines: int) -> str:
    """A finished run whose executed questions return the given row counts."""
    graph = stetiq.InMemoryGraphSource()
    graph.add_query_result(TECHNICIANS, [{"n": i} for i in range(technicians)])
    graph.add_query_result(MACHINES, [{"n": i} for i in range(machines)])
    runs = stetiq.Client(client.tracking_uri, graph_source=graph)
    with runs.start_run("plant") as run:
        pass
    return run.id


def plant_consumer_gates(client: stetiq.Client) -> dict[str, Any]:
    """`plant`, whose Use Case declares a Consumer Gate on three Consumers and none on the
    Planning team. Run 1 (the baseline) finds 5 breakdown technicians, run 2 finds 2: the
    Reliability dashboard's `triage-rows-hold` failed (5 -> 2, a 60% drop against 10% allowed), the
    Maintenance assistant's passed, and the Safety team was never evaluated."""
    client.create_knowledge_graph("plant", ontology=PLANT_ONTOLOGY)
    client.bind_graph_source("plant", GraphSourceScope(database="neo4j"))
    client.register_use_case("plant", PLANT_USE_CASE)
    baseline = _run(client, technicians=5, machines=4)
    candidate = _run(client, technicians=2, machines=4)
    client.evaluate_consumer_gates("plant", consumer="reliability-dashboard")
    client.evaluate_consumer_gates("plant", consumer="maintenance-assistant")
    return {"baseline_run": baseline, "candidate_run": candidate}


SCENARIOS: tuple[Scenario, ...] = (plant_consumer_gates,)
