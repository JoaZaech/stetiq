"""Construction Runs: the runs list, a run's page and comparing runs."""

from __future__ import annotations

from datetime import date
from typing import Any

import stetiq
from stetiq.graph_source import GraphSourceScope

from ._shared import SUPPORT_V1, Scenario, issue_token

RUNS_USE_CASE = """
description: Support agents triage tickets
competency_questions:
  - id: customer-names
    question: What are our customers called?
    query: MATCH (c:Customer) RETURN c.name AS name
    expected_answer: [Ada]
  - id: open-tickets
    question: Which tickets are open?
    query: MATCH (t:Ticket) RETURN t
"""


def _runs_client(client: stetiq.Client) -> stetiq.Client:
    """A Client on `client`'s database over the Graph Source of `construction_runs`."""
    graph = stetiq.InMemoryGraphSource()
    ada = graph.add_node(["Customer"], {"name": "Ada"})
    ticket = graph.add_node(["Ticket"], {"opened_at": date(2026, 1, 1), "priority": 2})
    graph.add_relationship(ada, "OPENED", ticket)
    graph.add_relationship(ticket, "ESCALATED", ada)
    graph.add_query_result("MATCH (c:Customer) RETURN c.name AS name", [{"name": "Ada"}])
    return stetiq.Client(client.tracking_uri, graph_source=graph)


def construction_runs(_client: stetiq.Client) -> dict[str, Any]:
    """Construction Runs of two Knowledge Graphs over the same Graph Source, which holds a
    `Ticket.priority` and an `ESCALATED` relationship no Ontology declares:

    - `support` (evolving), with a Use Case whose Competency Questions have queries:
      `finished`, a run with params and metrics that ended and produced Candidate v2
      (`customer-names` passes, `open-tickets` errors: its query has no result);
      `aborted`, a run that failed before observing anything;
    - `orders` (strict): `strict_failed`, a run that failed because it observed
      Concepts its Declared Ontology lacks.

    The canned query rows hold instance data ("Ada") that the UI must never show.
    """
    client = _runs_client(_client)
    scope = GraphSourceScope(database="neo4j")
    client.create_knowledge_graph("support", ontology=SUPPORT_V1)
    client.register_use_case("support", RUNS_USE_CASE)
    client.bind_graph_source("support", scope)
    with client.start_run("support", ontology_version=1) as run:
        run.log_params({"extractor": "llm", "temperature": 0.2})
        run.log_metrics({"precision": 0.91, "recall": 0.8})
    finished = run.id
    aborted = client.start_run("support", ontology_version=1)
    aborted.log_params({"extractor": "rules"})
    aborted.fail()

    client.create_knowledge_graph("orders", ontology=SUPPORT_V1)
    client.set_evolution_mode("orders", "strict")
    client.bind_graph_source("orders", scope)
    with client.start_run("orders", ontology_version=1) as run:
        pass
    return {"finished": finished, "aborted": aborted.id, "strict_failed": run.id}


def construction_runs_reader(client: stetiq.Client) -> dict[str, Any]:
    """`construction_runs`, plus a token for grace that can read `support` only."""
    seeded = construction_runs(client)
    return {**seeded, "grace": issue_token(client, "grace", {"support": "read"})}


def compared_runs(client: stetiq.Client) -> dict[str, Any]:
    """`construction_runs`, plus `rerun`: a second finished `support` run over the same
    graph with the same extractor and recall as `finished`, but another temperature
    and precision."""
    seeded = construction_runs(client)
    with _runs_client(client).start_run("support", ontology_version=1) as run:
        run.log_params({"extractor": "llm", "temperature": 0.5})
        run.log_metrics({"precision": 0.85, "recall": 0.8})
    return {**seeded, "rerun": run.id}


SCENARIOS: tuple[Scenario, ...] = (construction_runs, construction_runs_reader, compared_runs)
