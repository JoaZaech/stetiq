"""Observation of Vocabulary values, through the SDK, against the in-memory fake Graph Source.

Observation reads the values of Vocabulary-bound Attributes only: those of the Contract
Alias's Ontology Version for `observe`, and of the Declared Ontology when a run ends.
"""

import pytest

from stetiq.graph_source import GraphSourceScope, ObservedValues, ValueCount

WORK_ORDERS = """
vocabularies:
  - label: Status
    values: [open, closed]
  - label: Channel
    values: [email, phone]
node_types:
  - label: WorkOrder
    properties:
      - {name: status, type: STRING, vocabulary: Status}
      - {name: note, type: STRING}
  - label: Team
    properties:
      - {name: name, type: STRING}
relationship_types:
  - label: ASSIGNED_TO
    properties:
      - {name: channel, type: STRING, vocabulary: Channel}
patterns:
  - [WorkOrder, ASSIGNED_TO, Team]
"""


@pytest.fixture
def work_orders(client):
    client.create_knowledge_graph("plant", ontology=WORK_ORDERS)
    client.bind_graph_source("plant", GraphSourceScope(database="neo4j"))
    return "plant"


def seed(graph_source):
    team = graph_source.add_node(["Team"], {"name": "Maintenance"})
    for status, note, channel in [
        ("open", "pump leaks", "email"),
        ("closed", "fixed", "email"),
        ("open", "belt worn", "phone"),
        ("on_hold", "waiting for parts", "radio"),
    ]:
        order = graph_source.add_node(["WorkOrder"], {"status": status, "note": note})
        graph_source.add_relationship(order, "ASSIGNED_TO", team, {"channel": channel})


def values_by_attribute(schema):
    return {
        (owner.label, p.name): p.values
        for owner in (*schema.node_types, *schema.relationship_types)
        for p in owner.properties
    }


EXPECTED_VALUES = {
    ("WorkOrder", "status"): ObservedValues(
        (ValueCount("open", 2), ValueCount("closed", 1), ValueCount("on_hold", 1))
    ),
    ("WorkOrder", "note"): None,
    ("Team", "name"): None,
    ("ASSIGNED_TO", "channel"): ObservedValues(
        (ValueCount("email", 2), ValueCount("phone", 1), ValueCount("radio", 1))
    ),
}


def test_an_observation_stores_the_values_of_the_contracts_bound_attributes(
    client, work_orders, graph_source
):
    seed(graph_source)

    outcome = client.observe(work_orders)

    stored = client.get_observation(outcome.observation.id)
    assert values_by_attribute(stored.schema) == EXPECTED_VALUES


def test_an_ended_run_stores_the_values_of_its_declared_ontologys_bound_attributes(
    client, graph_source
):
    # The contract (v1) binds nothing; the run declares v2, which binds the Attributes.
    unbound = WORK_ORDERS.replace(", vocabulary: Status", "").replace(", vocabulary: Channel", "")
    client.create_knowledge_graph("plant", ontology=unbound)
    declared = client.register_ontology("plant", WORK_ORDERS)
    client.bind_graph_source("plant", GraphSourceScope(database="neo4j"))
    seed(graph_source)

    with client.start_run("plant", ontology_version=declared.number) as run:
        pass

    observation = client.get_observation(client.get_run(run.id).observation_id)
    assert values_by_attribute(observation.schema) == EXPECTED_VALUES


class AdapterWrittenBeforeVocabularies:
    """A Graph Source adapter whose `observe` takes only the scope."""

    def __init__(self, graph_source):
        self._graph_source = graph_source

    def observe(self, scope):
        return self._graph_source.observe(scope)


def test_an_ontology_without_vocabularies_observes_as_before(
    client_factory, support_ontology, graph_source
):
    client = client_factory(graph_source=AdapterWrittenBeforeVocabularies(graph_source))
    client.create_knowledge_graph("support", ontology=support_ontology)
    client.bind_graph_source("support", GraphSourceScope(database="neo4j"))
    graph_source.add_node(["Customer"], {"name": "Ada"})

    outcome = client.observe("support")
    with client.start_run("support") as run:
        pass

    run_observation = client.get_observation(client.get_run(run.id).observation_id)
    for observation in (outcome.observation, run_observation):
        assert observation.schema.to_dict()["node_types"] == [
            {
                "label": "Customer",
                "count": 1,
                "properties": [{"name": "name", "types": ["STRING"], "count": 1, "fill_rate": 1.0}],
            }
        ]


def test_the_cap_on_distinct_values_is_set_per_client(client_factory, work_orders, graph_source):
    seed(graph_source)

    outcome = client_factory(value_cap=2).observe(work_orders)

    status = outcome.observation.schema.node_type("WorkOrder").properties[1]
    assert status.values == ObservedValues(
        (ValueCount("open", 2), ValueCount("closed", 1)), truncated=True
    )
