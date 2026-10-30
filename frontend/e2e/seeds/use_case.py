"""Use Case Versions and their Competency Questions."""

from __future__ import annotations

from typing import Any

import stetiq

from ._shared import SUPPORT_USE_CASE, Scenario
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


SCENARIOS: tuple[Scenario, ...] = (support_use_case_versions,)
