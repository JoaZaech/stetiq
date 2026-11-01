"""Use Case Versions and their Competency Questions."""

from __future__ import annotations

from typing import Any

import stetiq

from ._shared import SUPPORT_USE_CASE, Scenario, issue_token
from .ontology_versions import support_lineage

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


SUPPORT_USE_CASE_WITH_CONSUMERS = (
    SUPPORT_USE_CASE_V2
    + """consumers:
  - id: triage-bot
    name: Triage bot
    kind: agent
    contact: Ada Lovelace
    description: Routes new tickets to the right team.
    tasks:
      - id: route-ticket
        description: Route a new ticket to an agent
        competency_questions: [customer-names, agent-names]
      - id: greet-customer
        description: Greet the customer by name
        competency_questions: [customer-names]
  - id: workload-dashboard
    name: Workload dashboard
    tasks:
      - id: show-agents
        description: List the agents on shift
"""
)


def support_use_case_consumers(client: stetiq.Client) -> dict[str, Any]:
    """`support_lineage`, with a Use Case whose two Consumers have Tasks: the Triage bot
    (every optional field set, two Tasks) and the Workload dashboard (only a name, and a
    Task that needs no Competency Question)."""
    seeded = support_lineage(client)
    client.register_use_case("support", SUPPORT_USE_CASE_WITH_CONSUMERS)
    return seeded


SUPPORT_USE_CASE_FOR_READINESS = (
    SUPPORT_USE_CASE_V2
    + """  - id: refund-amounts
    question: How much was refunded per ticket?
    concepts: [Refund.amount]
  - id: satisfaction
    question: How satisfied is each customer?
  - id: ticket-count
    question: How many tickets are there?
    concepts: [Ticket]
consumers:
  - id: triage-bot
    name: Triage bot
    tasks:
      - id: route-ticket
        description: Route a new ticket to an agent
        competency_questions: [customer-names, agent-names, refund-amounts, satisfaction]
"""
)


def support_task_readiness(client: stetiq.Client) -> dict[str, Any]:
    """`support_lineage`, with a Use Case whose Triage bot has one Task needing four
    questions: two answerable on the latest Ontology Version (v3), `refund-amounts`
    unanswerable and `satisfaction` unmapped. `ticket-count` serves no Task."""
    seeded = support_lineage(client)
    client.register_use_case("support", SUPPORT_USE_CASE_FOR_READINESS)
    return seeded


def support_use_case_consumers_reader(client: stetiq.Client) -> dict[str, Any]:
    """`support_use_case_consumers`, with a token for grace that can only read `support`."""
    seeded = support_use_case_consumers(client)
    return {**seeded, "grace": issue_token(client, "grace", {"support": "read"})}


SCENARIOS: tuple[Scenario, ...] = (
    support_use_case_versions,
    support_use_case_consumers,
    support_task_readiness,
    support_use_case_consumers_reader,
)
