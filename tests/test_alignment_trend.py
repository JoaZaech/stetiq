"""The alignment trend: a Conformance score on every on-demand Observation, plotted in time
order with the Construction Runs' scores. It has no threshold and raises no Drift.

Every test runs through the `client` fixture, so in every tracking mode (local, remote over
REST, Postgres)."""

from datetime import date

import pytest

from stetiq.graph_source import GraphSourceScope

AGENT = "  - label: Agent\n    properties:\n      - name: name\n        type: STRING\n"


@pytest.fixture
def support_kg(client, support_ontology):
    client.create_knowledge_graph("support", ontology=support_ontology)
    client.bind_graph_source("support", GraphSourceScope(database="neo4j"))
    return "support"


def seed_conforming_graph(graph_source):
    """Exactly the support ontology: Customer(name)-[OPENED]->Ticket(opened_at)."""
    ada = graph_source.add_node(["Customer"], {"name": "Ada"})
    ticket = graph_source.add_node(["Ticket"], {"opened_at": date(2026, 1, 1)})
    graph_source.add_relationship(ada, "OPENED", ticket)


def test_an_on_demand_observation_is_scored_against_the_contract_alias_version(
    client, support_kg, graph_source, support_ontology
):
    seed_conforming_graph(graph_source)
    graph_source.add_node(["Agent"], {"name": "Grace"})
    v2 = client.register_ontology(
        support_kg, support_ontology.replace("relationship_types:", AGENT + "relationship_types:")
    )

    before = client.observe(support_kg).observation
    client.set_alias(support_kg, "staging", v2.number)
    client.set_contract_alias(support_kg, "staging")
    after = client.observe(support_kg).observation

    assert (before.ontology_version, after.ontology_version) == (1, 2)
    assert before.conformance.score < 1.0
    assert [m.subject for m in before.conformance.undeclared] == ["Agent", "Agent.name"]
    assert after.conformance.score == 1.0
    assert client.get_observation(before.id) == before
    assert client.list_observations(support_kg) == [before, after]


def test_the_trend_puts_run_and_on_demand_scores_in_time_order(client, support_kg, graph_source):
    seed_conforming_graph(graph_source)
    first = client.observe(support_kg).observation
    graph_source.add_node(["Agent"], {"name": "Grace"})
    with client.start_run(support_kg) as run:  # evolving: judged against its Candidate, v2
        pass
    last = client.observe(support_kg).observation  # still judged against production, v1

    trend = client.alignment_trend(support_kg)

    ended = client.get_run(run.id)
    assert [(p.run_id, p.observation_id, p.ontology_version) for p in trend] == [
        (None, first.id, 1),
        (run.id, ended.observation_id, 2),
        (None, last.id, 1),
    ]
    assert [p.score for p in trend] == [1.0, 1.0, last.conformance.score]
    assert last.conformance.score < 1.0
    assert [p.at for p in trend] == [first.observed_at, ended.ended_at, last.observed_at]
