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
from stetiq.drift import DriftThresholds
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


def many_knowledge_graphs(client: stetiq.Client) -> dict[str, Any]:
    """Seven Knowledge Graphs, `alpha` to `golf`, created in that order; then `beta` gets
    a v2, so by last modified they run beta, golf, foxtrot, echo, delta, charlie, alpha."""
    for kg in ("alpha", "beta", "charlie", "delta", "echo", "foxtrot", "golf"):
        client.create_knowledge_graph(kg, ontology=ONTOLOGY)
    client.register_ontology("beta", ONTOLOGY.replace("Ticket]", "Ticket, Agent]", 1))
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


# v4 (from v2): deprecates Agent, drops Ticket.opened_at and adds an ASSIGNED relation,
# so its Ontology Diff has a deprecating, a breaking and an additive change.
SUPPORT_V4 = (
    SUPPORT_V2.replace(
        "{label: Agent, parent: Party}", "{label: Agent, parent: Party, deprecated: true}"
    )
    .replace("    properties: [{name: opened_at, type: DATE}]\n", "")
    .replace("relationship_types: [OPENED]", "relationship_types: [OPENED, ASSIGNED]")
    .replace(
        "patterns: [[Customer, OPENED, Ticket]]",
        "patterns: [[Customer, OPENED, Ticket], [Ticket, ASSIGNED, Agent]]",
    )
)


def support_breaking_change(client: stetiq.Client) -> dict[str, Any]:
    """`support_lineage`, plus v4: a deprecating, a breaking and an additive change from v2."""
    seeded = support_lineage(client)
    client.register_ontology("support", SUPPORT_V4)
    return seeded


class ReviewScore(stetiq.OntologyVersionEvaluator):
    """A custom Evaluator scoring each version with a fixed `review/score`."""

    name = "review"

    def __init__(self, scores: dict[int, float]) -> None:
        self._scores = scores

    def evaluate(self, version: stetiq.OntologyVersion) -> stetiq.Evaluation:
        return stetiq.Evaluation(metrics={"score": self._scores[version.number]})


def support_metrics(client: stetiq.Client) -> dict[str, Any]:
    """`support_lineage`, plus a custom `review` Evaluator scoring v1 0.9 and v3 0.7;
    v2 has no `review/score`."""
    seeded = support_lineage(client)
    review = ReviewScore({1: 0.9, 3: 0.7})
    for number in (1, 3):
        client.evaluate("support", number, evaluators=[review])
    return seeded


def described_support(client: stetiq.Client) -> dict[str, Any]:
    """`support_lineage` with a markdown description, a token for ada that can edit
    `support` and one for grace that can only read it."""
    seeded = support_lineage(client)
    client.set_knowledge_graph_description(
        "support", "Answers **support** questions.\n\n- triage\n- escalation"
    )
    return {
        **seeded,
        "ada": issue_token(client, "ada", {"support": "edit"}),
        "grace": issue_token(client, "grace", {"support": "read"}),
    }


SUPPORT_USE_CASE_V2 = (
    SUPPORT_USE_CASE
    + """  - id: agent-names
    question: What are our agents called?
    concepts: [Agent.name]
"""
)

SUPPORT_USE_CASE_V3 = """
description: Support agents triage and answer tickets
competency_questions:
  - id: customer-names
    question: What is each customer called?
    concepts: [Customer.name]
  - id: ticket-dates
    question: When was each ticket opened?
    query: MATCH (t:Ticket) RETURN t.opened_at
    expected_answer: [{opened_at: "2026-01-01"}]
    concepts: [Ticket.opened_at]
"""


def support_use_case_versions(client: stetiq.Client) -> dict[str, Any]:
    """`support_lineage`, with three Use Case Versions: v1 asks `customer-names`, v2 adds
    `agent-names`, v3 rewords `customer-names`, drops `agent-names`, adds `ticket-dates`
    and changes the description."""
    seeded = support_lineage(client)
    client.register_use_case("support", SUPPORT_USE_CASE_V2)
    client.register_use_case("support", SUPPORT_USE_CASE_V3)
    return seeded


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


# For the Ontology Map: two relations between Customer and Ticket, a self-loop, Agent and
# Customer under Party, and a deprecated class (LegacyTicket) and relation (FILED).
MAP_ONTOLOGY = """
node_types:
  - {label: Agent, parent: Party}
  - {label: Customer, parent: Party}
  - {label: LegacyTicket, parent: Ticket, deprecated: true}
  - Party
  - Product
  - Ticket
relationship_types: [ABOUT, DUPLICATES, {label: FILED, deprecated: true}, FOLLOWS, OPENED]
patterns:
  - [Customer, OPENED, Ticket]
  - [Customer, FOLLOWS, Ticket]
  - [Ticket, ABOUT, Product]
  - [Ticket, DUPLICATES, Ticket]
  - [Customer, FILED, LegacyTicket]
"""


# MAP_ONTOLOGY's next version: Queue and IN_QUEUE added (additive), Product and ABOUT
# removed (breaking), and Ticket given a required property (breaking).
MAP_ONTOLOGY_V2 = """
node_types:
  - {label: Agent, parent: Party}
  - {label: Customer, parent: Party}
  - {label: LegacyTicket, parent: Ticket, deprecated: true}
  - Party
  - Queue
  - label: Ticket
    properties: [{name: priority, type: STRING, required: true}]
relationship_types: [DUPLICATES, {label: FILED, deprecated: true}, FOLLOWS, IN_QUEUE, OPENED]
patterns:
  - [Customer, OPENED, Ticket]
  - [Customer, FOLLOWS, Ticket]
  - [Ticket, DUPLICATES, Ticket]
  - [Customer, FILED, LegacyTicket]
  - [Ticket, IN_QUEUE, Queue]
"""


# MAP_ONTOLOGY_V2's next version: Team and MEMBER_OF added (additive), and Queue
# deprecated (deprecating). Against v1, Queue is an addition instead.
MAP_ONTOLOGY_V3 = """
node_types:
  - {label: Agent, parent: Party}
  - {label: Customer, parent: Party}
  - {label: LegacyTicket, parent: Ticket, deprecated: true}
  - Party
  - {label: Queue, deprecated: true}
  - Team
  - label: Ticket
    properties: [{name: priority, type: STRING, required: true}]
relationship_types:
  [DUPLICATES, {label: FILED, deprecated: true}, FOLLOWS, IN_QUEUE, MEMBER_OF, OPENED]
patterns:
  - [Customer, OPENED, Ticket]
  - [Customer, FOLLOWS, Ticket]
  - [Ticket, DUPLICATES, Ticket]
  - [Customer, FILED, LegacyTicket]
  - [Ticket, IN_QUEUE, Queue]
  - [Agent, MEMBER_OF, Team]
"""


def ontology_map(client: stetiq.Client) -> dict[str, Any]:
    """Knowledge Graph `support` with v1 = `MAP_ONTOLOGY`, v2 = `MAP_ONTOLOGY_V2` and
    v3 = `MAP_ONTOLOGY_V3`."""
    client.create_knowledge_graph("support", ontology=MAP_ONTOLOGY)
    client.register_ontology("support", MAP_ONTOLOGY_V2)
    client.register_ontology("support", MAP_ONTOLOGY_V3)
    return {}


# Two Patterns of one relation: v2 adds (Agent)-[OPENED]->(Ticket) beside v1's
# (Customer)-[OPENED]->(Ticket), so the Diff records an endpoint change against OPENED.
MAP_PATTERNS_V1 = """
node_types: [Agent, Customer, Ticket]
relationship_types: [OPENED]
patterns: [[Customer, OPENED, Ticket]]
"""

MAP_PATTERNS_V2 = MAP_PATTERNS_V1.replace(
    "patterns: [[Customer, OPENED, Ticket]]",
    "patterns: [[Agent, OPENED, Ticket], [Customer, OPENED, Ticket]]",
)


def ontology_map_patterns(client: stetiq.Client) -> dict[str, Any]:
    """Knowledge Graph `support` with v1 = `MAP_PATTERNS_V1` and v2 = `MAP_PATTERNS_V2`."""
    client.create_knowledge_graph("support", ontology=MAP_PATTERNS_V1)
    client.register_ontology("support", MAP_PATTERNS_V2)
    return {}


# For selecting on the Ontology Map: a superclass, properties, a constraint, a described relation.
MAP_DETAILS_ONTOLOGY = """
node_types:
  - label: Party
    properties: [{name: name, type: STRING, required: true}]
  - label: Customer
    parent: Party
    description: Someone who opens tickets
    properties: [{name: email, type: STRING}]
  - {label: Product}
  - label: Ticket
    properties: [{name: opened_at, type: DATE}]
relationship_types:
  - label: OPENED
    description: The customer opened the ticket
    properties: [{name: channel, type: STRING}]
  - {label: ABOUT}
patterns:
  - [Customer, OPENED, Ticket]
  - [Ticket, ABOUT, Product]
constraints:
  - {type: UNIQUENESS, node_type: Customer, property_name: email}
"""


def ontology_map_details(client: stetiq.Client) -> dict[str, Any]:
    """Knowledge Graph `support` with v1 = `MAP_DETAILS_ONTOLOGY`."""
    client.create_knowledge_graph("support", ontology=MAP_DETAILS_ONTOLOGY)
    return {}


# For paths on the Ontology Map: Customer reaches Address only through its superclass Party's
# Pattern, and nothing connects Agent.
MAP_PATH_ONTOLOGY = """
node_types:
  - {label: Address}
  - {label: Agent}
  - {label: Party}
  - {label: Customer, parent: Party}
  - {label: Product}
  - {label: Ticket}
relationship_types:
  - {label: ABOUT}
  - {label: LIVES_AT}
  - {label: OPENED}
patterns:
  - [Customer, OPENED, Ticket]
  - [Party, LIVES_AT, Address]
  - [Ticket, ABOUT, Product]
"""


def ontology_map_path(client: stetiq.Client) -> dict[str, Any]:
    """Knowledge Graph `support` with v1 = `MAP_PATH_ONTOLOGY`."""
    client.create_knowledge_graph("support", ontology=MAP_PATH_ONTOLOGY)
    return {}


def ontology_map_large(client: stetiq.Client) -> dict[str, Any]:
    """Knowledge Graph `support` with v1 = 60 classes in a ring, each related to the next:
    an Ontology too big for the Map's viewport at a readable zoom."""
    labels = [f"Class{i:02}" for i in range(60)]
    ontology = {
        "node_types": labels,
        "relationship_types": ["NEXT"],
        "patterns": [[a, "NEXT", b] for a, b in zip(labels, labels[1:] + labels[:1], strict=True)],
    }
    # JSON is YAML.
    client.create_knowledge_graph("support", ontology=json.dumps(ontology))
    return {}


SCENARIOS: dict[str, Scenario] = {
    "construction_runs": construction_runs,
    "construction_runs_reader": construction_runs_reader,
    "empty": empty,
    "knowledge_graphs": knowledge_graphs,
    "many_knowledge_graphs": many_knowledge_graphs,
    "signed_in_users": signed_in_users,
    "support_lineage": support_lineage,
    "support_lineage_reader": support_lineage_reader,
    "support_breaking_change": support_breaking_change,
    "support_metrics": support_metrics,
    "described_support": described_support,
    "support_use_case_versions": support_use_case_versions,
    "observed_support": observed_support,
    "compared_runs": compared_runs,
    "ontology_map": ontology_map,
    "ontology_map_details": ontology_map_details,
    "ontology_map_patterns": ontology_map_patterns,
    "ontology_map_path": ontology_map_path,
    "ontology_map_large": ontology_map_large,
}


def main(scenario: str, tracking_uri: str) -> None:
    if scenario not in SCENARIOS:
        sys.exit(f"unknown seed scenario {scenario!r}; known: {', '.join(SCENARIOS)}")
    client = stetiq.Client(tracking_uri, graph_source=stetiq.InMemoryGraphSource())
    print(json.dumps(SCENARIOS[scenario](client)))


if __name__ == "__main__":
    main(*sys.argv[1:])
