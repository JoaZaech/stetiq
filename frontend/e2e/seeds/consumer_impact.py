"""The Consumer impact of an Ontology Diff."""

from __future__ import annotations

from typing import Any

import stetiq

from ._shared import Scenario
from .ontology_versions import support_breaking_change

# Judged against v2 -> v4 of `support_breaking_change`, which removes Ticket.opened_at
# (breaking) and deprecates Agent (deprecating).
SUPPORT_USE_CASE_IMPACT = """
competency_questions:
  - id: customer-names
    question: What are our customers called?
    concepts: [Customer.name]
  - id: ticket-dates
    question: When was each ticket opened?
    query: MATCH (t:Ticket) RETURN t.opened_at
  - id: agent-names
    question: What are our agents called?
    concepts: [Agent]
  - id: loyal-customers
    question: Which customers are the most loyal?
consumers:
  - id: triage-bot
    name: Triage bot
    kind: agent
    tasks:
      - id: route-ticket
        description: Route a new ticket by its age
        competency_questions: [customer-names, ticket-dates]
      - id: assign-agent
        description: Assign the ticket to an agent
        competency_questions: [agent-names]
  - id: crm-sync
    name: CRM sync
    tasks:
      - id: sync-names
        description: Copy customer names
        competency_questions: [customer-names]
  - id: workload-dashboard
    name: Workload dashboard
    tasks:
      - id: workload-chart
        description: Chart each agent's workload
        competency_questions: [agent-names]
"""


def support_consumer_impact(client: stetiq.Client) -> dict[str, Any]:
    """`support_breaking_change`, with a Use Case whose Consumers v2 -> v4 hits: Triage
    bot affected (`ticket-dates`) and will be affected (`agent-names`), Workload dashboard
    will be affected, CRM sync untouched, and `loyal-customers`, which no Task needs and
    nothing maps, of unknown impact."""
    seeded = support_breaking_change(client)
    client.register_use_case("support", SUPPORT_USE_CASE_IMPACT)
    return seeded


SCENARIOS: tuple[Scenario, ...] = (support_consumer_impact,)
