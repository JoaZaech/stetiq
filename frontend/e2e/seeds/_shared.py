"""Helpers and Ontologies that scenarios in several modules share."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import date
from typing import Any

import stetiq
from stetiq.auth import TokenRegistry

Scenario = Callable[[stetiq.Client], dict[str, Any]]


def issue_token(client: stetiq.Client, user: str, grants: dict[str, str]) -> dict[str, str]:
    """An API Token on the seeded database: `{"id", "value"}` (revoke it by `id`)."""
    token, value = TokenRegistry(client.tracking_uri).issue(user, grants)
    return {"id": token.id, "value": value}


def add_ada_and_ticket(
    graph: stetiq.InMemoryGraphSource,
    *,
    ada_labels: Sequence[str] = ("Customer",),
    ticket_labels: Sequence[str] = ("Ticket",),
    priority: int | None = 2,
) -> tuple[int, int]:
    """Customer Ada, a Ticket opened on 2026-01-01 (with `priority`, unless it is None)
    and Ada's `OPENED` relationship to it; returns `(ada, ticket)`."""
    ada = graph.add_node(ada_labels, {"name": "Ada"})
    ticket_properties: dict[str, Any] = {"opened_at": date(2026, 1, 1)}
    if priority is not None:
        ticket_properties["priority"] = priority
    ticket = graph.add_node(ticket_labels, ticket_properties)
    graph.add_relationship(ada, "OPENED", ticket)
    return ada, ticket


# The smallest Ontology: a single Customer node type.
CUSTOMER_ONLY = "node_types:\n  - label: Customer\n"


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
