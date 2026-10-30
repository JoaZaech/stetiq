"""Ontology Versions of `support`: the Ontology table and comparison, the Ontology Diff,
promotion and version metrics."""

from __future__ import annotations

from datetime import date
from typing import Any

import stetiq
from stetiq.graph_source import GraphSourceScope

from ._shared import SUPPORT_USE_CASE, SUPPORT_V1, SUPPORT_V2, Scenario, issue_token

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


SCENARIOS: tuple[Scenario, ...] = (
    support_lineage,
    support_lineage_reader,
    support_breaking_change,
    support_metrics,
)
