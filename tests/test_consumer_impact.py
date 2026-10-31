"""Consumer impact: which Consumers, Tasks and Competency Questions an Ontology Diff hits."""

import pytest
from fastapi.testclient import TestClient

from stetiq import Client, NoUseCaseError, UseCaseImpact
from stetiq.auth import TokenRegistry
from stetiq.server import create_app

KG = "support"

BASE = """
node_types:
  - label: Party
    properties:
      - {name: name, type: STRING}
  - {label: Customer, parent: Party}
  - label: Ticket
    properties:
      - {name: opened_at, type: DATE}
  - Agent
relationship_types: [OPENED, HANDLES]
patterns:
  - [Customer, OPENED, Ticket]
  - [Agent, HANDLES, Ticket]
"""

USE_CASE = """
competency_questions:
  - id: tickets-per-customer
    question: How many tickets has each customer opened?
    query: MATCH (c:Customer)-[:OPENED]->(t:Ticket) RETURN c.name, count(t)
  - id: ticket-dates
    question: When was each ticket opened?
    concepts: [Ticket.opened_at]
  - id: handlers
    question: Who handles which ticket?
    concepts: ["(Agent)-[HANDLES]->(Ticket)"]
  - id: loyal-customers
    question: Which customers are the most loyal?
  - id: agent-names
    question: What are our agents called?
    concepts: [Agent]
consumers:
  - id: triage-bot
    name: Triage bot
    kind: agent
    tasks:
      - id: route-ticket
        description: Route a new ticket by its customer
        competency_questions: [tickets-per-customer, ticket-dates]
  - id: workload-dashboard
    name: Workload dashboard
    tasks:
      - id: workload-chart
        description: Chart each agent's workload
        competency_questions: [handlers]
"""


@pytest.fixture
def impact(client):
    """Register BASE as v1 and USE_CASE, then the impact of evolving to `evolved`."""
    client.create_knowledge_graph(KG, ontology=BASE)
    client.register_use_case(KG, USE_CASE)

    def _impact(evolved: str):
        version = client.register_ontology(KG, evolved)
        return client.consumer_impact(KG, 1, version.number)

    return _impact


def outline(impact) -> list[tuple]:
    """Consumer -> Task -> question, each with its level, and the causing changes' concepts."""
    return [
        (
            c.id,
            c.level,
            [
                (
                    t.id,
                    t.level,
                    [(q.id, q.level, [ch.concept for ch in q.changes]) for q in t.questions],
                )
                for t in c.tasks
            ],
        )
        for c in impact.consumers
    ]


def test_a_breaking_change_puts_the_consumers_that_need_it_in_affected(impact):
    result = impact(
        BASE.replace("OPENED, HANDLES]", "HANDLES]").replace("  - [Customer, OPENED, Ticket]\n", "")
    )

    assert outline(result) == [
        (
            "triage-bot",
            "affected",
            [("route-ticket", "affected", [("tickets-per-customer", "affected", ["OPENED"])])],
        ),
    ]


def test_a_deprecating_change_puts_them_in_will_be_affected(impact):
    result = impact(BASE.replace("  - Agent\n", "  - {label: Agent, deprecated: true}\n"))

    assert outline(result) == [
        (
            "workload-dashboard",
            "will_be_affected",
            [("workload-chart", "will_be_affected", [("handlers", "will_be_affected", ["Agent"])])],
        ),
    ]
    assert [c.id for c in result.by_level("will_be_affected")] == ["workload-dashboard"]
    assert result.by_level("affected") == ()


def test_cosmetic_and_additive_changes_hit_no_one(impact):
    result = impact(
        BASE.replace("  - Agent\n", "  - Agent\n  - Product\n").replace(
            "{name: opened_at, type: DATE}",
            "{name: opened_at, type: DATE, description: When it was opened}",
        )
    )

    assert result.consumers == ()
    assert result.no_consumer == ()


def test_questions_no_task_needs_are_under_no_consumer_and_unmapped_ones_are_unknown(impact):
    result = impact(BASE.replace("  - Agent\n", "  - {label: Agent, deprecated: true}\n"))

    assert [(q.id, q.level, [c.concept for c in q.changes]) for q in result.no_consumer] == [
        ("agent-names", "will_be_affected", ["Agent"]),
        ("loyal-customers", "unknown", []),
    ]


def test_a_question_takes_its_most_severe_change_and_lists_every_one(impact):
    result = impact(
        BASE.replace("  - Agent\n", "  - {label: Agent, deprecated: true}\n").replace(
            "[Agent, HANDLES, Ticket]", "[Party, HANDLES, Ticket]"
        )
    )

    [dashboard] = result.consumers
    [task] = dashboard.tasks
    [question] = task.questions
    assert (dashboard.level, task.level, question.level) == ("affected",) * 3
    assert [c.detail for c in question.changes] == [
        "deprecated",
        "endpoint pattern (Agent)-[HANDLES]->(Ticket) removed",
    ]


def test_an_attribute_change_hits_questions_on_a_type_that_inherits_it(impact):
    result = impact(BASE.replace("      - {name: name, type: STRING}\n", ""))

    assert outline(result) == [
        (
            "triage-bot",
            "affected",
            [
                (
                    "route-ticket",
                    "affected",
                    [("tickets-per-customer", "affected", ["Party.name"])],
                )
            ],
        ),
    ]


def test_an_endpoint_pattern_change_hits_only_the_paths_it_serves(client):
    base = BASE.replace(
        "  - [Agent, HANDLES, Ticket]\n",
        "  - [Agent, HANDLES, Ticket]\n  - [Customer, HANDLES, Ticket]\n",
    )
    client.create_knowledge_graph(KG, ontology=base)
    client.register_use_case(KG, USE_CASE)
    client.register_ontology(KG, BASE)

    assert [c.detail for c in client.diff_ontology_versions(KG, 1, 2).breaking] == [
        "endpoint pattern (Customer)-[HANDLES]->(Ticket) removed"
    ]
    result = client.consumer_impact(KG, 1, 2)
    assert result.consumers == ()
    assert [(q.id, q.level) for q in result.no_consumer] == [("loyal-customers", "unknown")]


def test_without_a_use_case_the_impact_says_there_is_none(client):
    client.create_knowledge_graph(KG, ontology=BASE)
    client.register_ontology(
        KG, BASE.replace("  - Agent\n", "  - {label: Agent, deprecated: true}\n")
    )

    with pytest.raises(NoUseCaseError):
        client.consumer_impact(KG, 1, 2)


def test_versions_default_to_the_contract_version_and_the_latest_candidate(impact, client):
    impact(BASE.replace("  - Agent\n", "  - {label: Agent, deprecated: true}\n"))

    assert [c.id for c in client.consumer_impact(KG).consumers] == ["workload-dashboard"]


def test_the_impact_is_judged_against_the_use_case_version_asked_for(impact, client):
    impact(BASE.replace("  - Agent\n", "  - {label: Agent, deprecated: true}\n"))
    client.register_use_case(
        KG, "competency_questions: [{id: tickets, question: Which tickets, concepts: [Ticket]}]\n"
    )

    assert client.consumer_impact(KG, 1, 2) == UseCaseImpact()
    assert [c.id for c in client.consumer_impact(KG, 1, 2, use_case_version=1).consumers] == [
        "workload-dashboard"
    ]


# --- The route the web UI reads (raw HTTP) --------------------------------------------------


@pytest.fixture
def database_url(tmp_path):
    return f"sqlite:///{tmp_path / 'server.db'}"


@pytest.fixture
def http(database_url):
    with TestClient(create_app(database_url)) as c:
        yield c


def reader(database_url, grants):
    return {"Authorization": f"Bearer {TokenRegistry(database_url).issue('ada', grants)[1]}"}


def get_impact(http, headers, **params):
    return http.get(
        f"/api/v1/knowledge-graphs/{KG}/consumer-impact", params=params, headers=headers
    )


def test_the_route_returns_the_impact_for_explicit_versions(http, database_url):
    sdk = Client(database_url)
    sdk.create_knowledge_graph(KG, ontology=BASE)
    sdk.register_use_case(KG, USE_CASE)
    sdk.register_ontology(KG, BASE.replace("  - Agent\n", "  - {label: Agent, deprecated: true}\n"))

    r = get_impact(http, reader(database_url, {KG: "read"}), base=1, target=2)

    assert r.status_code == 200, r.text
    deprecated_agent = {
        "concept": "Agent",
        "concept_kind": "node_type",
        "kind": "deprecated",
        "classification": "deprecating",
        "detail": "deprecated",
    }
    assert r.json() == {
        "consumers": [
            {
                "id": "workload-dashboard",
                "name": "Workload dashboard",
                "kind": None,
                "level": "will_be_affected",
                "tasks": [
                    {
                        "id": "workload-chart",
                        "description": "Chart each agent's workload",
                        "level": "will_be_affected",
                        "questions": [
                            {
                                "id": "handlers",
                                "question": "Who handles which ticket?",
                                "level": "will_be_affected",
                                "changes": [deprecated_agent],
                            }
                        ],
                    }
                ],
            }
        ],
        "no_consumer": [
            {
                "id": "agent-names",
                "question": "What are our agents called?",
                "level": "will_be_affected",
                "changes": [deprecated_agent],
            },
            {
                "id": "loyal-customers",
                "question": "Which customers are the most loyal?",
                "level": "unknown",
                "changes": [],
            },
        ],
    }
    pinned = get_impact(
        http, reader(database_url, {KG: "read"}), base=1, target=2, use_case_version=1
    )
    assert pinned.json() == r.json()


def test_the_route_says_when_there_is_no_use_case(http, database_url):
    Client(database_url).create_knowledge_graph(KG, ontology=BASE)

    r = get_impact(http, reader(database_url, {KG: "read"}), base=1, target=1)

    assert r.status_code == 404
    assert r.json()["error"]["type"] == "NoUseCaseError"


def test_the_route_needs_read_permission_on_the_knowledge_graph(http, database_url):
    Client(database_url).create_knowledge_graph(KG, ontology=BASE)

    r = get_impact(http, reader(database_url, {"billing": "read"}), base=1, target=1)

    assert r.status_code == 403
