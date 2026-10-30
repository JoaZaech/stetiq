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
from datetime import date
from typing import Any

import stetiq
from stetiq.auth import TokenRegistry
from stetiq.graph_source import GraphSourceScope

Scenario = Callable[[stetiq.Client], dict[str, Any]]


def issue_token(client: stetiq.Client, user: str, grants: dict[str, str]) -> dict[str, str]:
    """An API Token on the seeded database: `{"id", "value"}` (revoke it by `id`)."""
    token, value = TokenRegistry(client.tracking_uri).issue(user, grants)
    return {"id": token.id, "value": value}


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


def signed_in_users(client: stetiq.Client) -> dict[str, Any]:
    """`support` and `billing`, and a token for ada: edit on `support`, read on `billing`."""
    for kg in ("support", "billing"):
        client.create_knowledge_graph(kg, ontology="node_types:\n  - label: Customer\n")
    return {"ada": issue_token(client, "ada", {"support": "edit", "billing": "read"})}


SUPPORT_V1 = """
node_types:
  - label: Party
    properties: [{name: name, type: STRING, required: true}]
  - {label: Customer, parent: Party, description: Someone who opens tickets}
  - label: Ticket
    properties: [{name: opened_at, type: DATE}]
relationship_types: [OPENED]
patterns: [[Customer, OPENED, Ticket]]
constraints:
  - {type: UNIQUENESS, node_type: Customer, property_name: name}
"""

# v2 adds an Agent class under Party: an additive change.
SUPPORT_V2 = SUPPORT_V1.replace(
    "  - label: Ticket\n", "  - {label: Agent, parent: Party}\n  - label: Ticket\n"
)

SUPPORT_USE_CASE = """
description: Support agents triage tickets
competency_questions:
  - id: customer-names
    question: What are our customers called?
    concepts: [Customer.name]
"""

NO_BREAKING_GATE = """
gates:
  - name: no-breaking-changes
    check: ontology_diff
    max_classification: deprecating
"""


def support_lineage(_client: stetiq.Client) -> dict[str, Any]:
    """Knowledge Graph `support` with three Ontology Versions:

    - v1, registered on creation, `production` (the Contract Alias) points to it;
    - v2, registered by hand with a Use Case, `staging` points to it, its Gate passed;
    - v3, a Candidate produced by an evolving Construction Run (origin `run`).
    """
    graph = stetiq.InMemoryGraphSource()
    client = stetiq.Client(_client.tracking_uri, graph_source=graph)
    client.create_knowledge_graph("support", ontology=SUPPORT_V1)
    client.register_use_case("support", SUPPORT_USE_CASE)
    client.register_ontology("support", SUPPORT_V2)
    client.set_alias("support", "staging", 2)
    client.evaluate_gates("support", NO_BREAKING_GATE, version=2)

    client.bind_graph_source("support", GraphSourceScope(database="neo4j"))
    ada = graph.add_node(["Customer"], {"name": "Ada"})
    ticket = graph.add_node(["Ticket"], {"opened_at": date(2026, 1, 1), "priority": 2})
    graph.add_relationship(ada, "OPENED", ticket)
    with client.start_run("support", ontology_version=2) as run:
        pass
    ended = client.get_run(run.id)
    return {"run_id": ended.id, "candidate_version": ended.candidate_version}


def support_lineage_reader(client: stetiq.Client) -> dict[str, Any]:
    """`support_lineage`, plus a `secret` Knowledge Graph and a token for grace that can
    read `support` only."""
    seeded = support_lineage(client)
    client.create_knowledge_graph("secret", ontology="node_types:\n  - label: Customer\n")
    return {**seeded, "grace": issue_token(client, "grace", {"support": "read"})}


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
    graph = stetiq.InMemoryGraphSource()
    client = stetiq.Client(_client.tracking_uri, graph_source=graph)
    scope = GraphSourceScope(database="neo4j")
    ada = graph.add_node(["Customer"], {"name": "Ada"})
    ticket = graph.add_node(["Ticket"], {"opened_at": date(2026, 1, 1), "priority": 2})
    graph.add_relationship(ada, "OPENED", ticket)
    graph.add_relationship(ticket, "ESCALATED", ada)
    graph.add_query_result("MATCH (c:Customer) RETURN c.name AS name", [{"name": "Ada"}])

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


SCENARIOS: dict[str, Scenario] = {
    "construction_runs": construction_runs,
    "construction_runs_reader": construction_runs_reader,
    "empty": empty,
    "knowledge_graphs": knowledge_graphs,
    "signed_in_users": signed_in_users,
    "support_lineage": support_lineage,
    "support_lineage_reader": support_lineage_reader,
}


def main(scenario: str, tracking_uri: str) -> None:
    if scenario not in SCENARIOS:
        sys.exit(f"unknown seed scenario {scenario!r}; known: {', '.join(SCENARIOS)}")
    client = stetiq.Client(tracking_uri, graph_source=stetiq.InMemoryGraphSource())
    print(json.dumps(SCENARIOS[scenario](client)))


if __name__ == "__main__":
    main(*sys.argv[1:])
