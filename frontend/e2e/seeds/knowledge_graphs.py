"""The Knowledge Graphs list and a Knowledge Graph's page and description."""

from __future__ import annotations

from typing import Any

import stetiq
from stetiq.graph_source import GraphSourceScope

from ._shared import Scenario, issue_token
from .ontology_versions import support_lineage


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


SCENARIOS: tuple[Scenario, ...] = (
    empty,
    knowledge_graphs,
    many_knowledge_graphs,
    described_support,
)
