import pytest
import yaml

import stetiq

# The same structure as conftest.SUPPORT_ONTOLOGY, written differently: other
# order of concepts/properties, flow style, explicit defaults.
SUPPORT_ONTOLOGY_REORDERED = """
relationship_types: [{label: OPENED, deprecated: false}]
patterns: [[Customer, OPENED, Ticket]]
node_types:
  - label: Ticket
    description: A support request
    properties: [{name: opened_at, type: DATE, required: false}]
  - {label: Customer, properties: [{name: name, type: STRING, required: true}]}
"""

WITH_AGENT = """
node_types:
  - label: Customer
    properties:
      - {name: name, type: STRING, required: true}
  - label: Ticket
    description: A support request
    properties:
      - {name: opened_at, type: DATE}
  - Agent
relationship_types: [OPENED, HANDLES]
patterns:
  - [Customer, OPENED, Ticket]
  - [Agent, HANDLES, Ticket]
"""


@pytest.fixture
def kg(client, support_ontology):
    return client.create_knowledge_graph("customer-support-kg", ontology=support_ontology)


def test_an_ontology_version_is_identified_by_a_content_hash(client, kg):
    version = client.get_ontology_version(kg.name, 1)

    # Golden value: the hash is a stable identity across stetiq releases; if the
    # canonical form ever changes, existing stores stop deduplicating.
    # sha256 of the hand-written canonical JSON (sorted keys, no whitespace, defaults omitted):
    # {"node_types":[{"label":"Customer","properties":[{"name":"name","required":true,
    #   "type":"STRING"}]},{"description":"A support request","label":"Ticket","properties":
    #   [{"name":"opened_at","type":"DATE"}]}],"patterns":[["Customer","OPENED","Ticket"]],
    #   "relationship_types":[{"label":"OPENED"}]}
    assert version.content_hash == (
        "3ca3bce46d49fec1e6ae8419972651606e728d6a96da099aa28355c613a3110b"
    )


def test_registering_identical_content_returns_the_existing_version(client, kg):
    again = client.register_ontology(kg.name, SUPPORT_ONTOLOGY_REORDERED)

    assert again.number == 1
    assert again == client.get_ontology_version(kg.name, 1)
    assert [v.number for v in client.list_ontology_versions(kg.name)] == [1]


def test_registering_changed_content_creates_a_new_version(client, kg):
    v2 = client.register_ontology(kg.name, WITH_AGENT)

    versions = client.list_ontology_versions(kg.name)

    assert v2.number == 2
    assert v2.content_hash != versions[0].content_hash
    assert [(v.number, v.origin) for v in versions] == [(1, "registered"), (2, "registered")]


def test_a_newly_registered_version_holds_its_ontology_in_canonical_form(client, kg):
    created = client.register_ontology(kg.name, WITH_AGENT)  # concepts not sorted by label

    assert created == client.get_ontology_version(kg.name, created.number)
    assert [n.label for n in created.ontology.node_types] == ["Agent", "Customer", "Ticket"]


def test_existing_versions_are_unchanged_by_later_registrations(client, kg):
    before = client.get_ontology_yaml(kg.name, 1)

    client.register_ontology(kg.name, WITH_AGENT)

    assert client.get_ontology_yaml(kg.name, 1) == before


def test_ontology_versions_are_immutable_values(client, kg):
    version = client.get_ontology_version(kg.name, 1)

    with pytest.raises(AttributeError):
        version.content_hash = "tampered"  # type: ignore[misc]


def test_identical_content_in_another_knowledge_graph_is_its_own_version(
    client, kg, support_ontology
):
    other = client.create_knowledge_graph("other-kg", ontology=support_ontology)

    assert client.list_ontology_versions(other.name)[0].knowledge_graph == "other-kg"
    assert [v.number for v in client.list_ontology_versions(kg.name)] == [1]


def test_a_version_is_fetched_back_as_yaml(client, kg):
    fetched = yaml.safe_load(client.get_ontology_yaml(kg.name, 1))

    assert fetched == {
        "node_types": [
            {"label": "Customer", "properties": [{"name": "name", "type": "STRING", "required": True}]},
            {
                "label": "Ticket",
                "description": "A support request",
                "properties": [{"name": "opened_at", "type": "DATE"}],
            },
        ],
        "relationship_types": [{"label": "OPENED"}],
        "patterns": [["Customer", "OPENED", "Ticket"]],
    }


def test_fetched_yaml_registers_back_to_the_same_version(client, kg):
    again = client.register_ontology(kg.name, client.get_ontology_yaml(kg.name, 1))

    assert again.number == 1


def test_deprecation_and_replacement_round_trip_through_fetch(client, kg):
    v2 = client.register_ontology(
        kg.name,
        """
node_types:
  - {label: Customer, deprecated: true, replacedBy: Client}
  - Client
  - Ticket
relationship_types:
  - {label: OPENED, deprecated: true}
  - {label: RAISED, replacedBy: OPENED}
patterns:
  - [Client, RAISED, Ticket]
""",
    )

    fetched = yaml.safe_load(client.get_ontology_yaml(kg.name, v2.number))
    ontology = client.get_ontology_version(kg.name, v2.number).ontology

    assert {"label": "Customer", "deprecated": True, "replacedBy": "Client"} in fetched["node_types"]
    assert {"label": "OPENED", "deprecated": True} in fetched["relationship_types"]
    assert {"label": "RAISED", "replacedBy": "OPENED"} in fetched["relationship_types"]
    assert ontology.node_type("Customer").replaced_by == "Client"
    assert ontology.relationship_type("OPENED").deprecated is True


def test_deprecating_a_concept_creates_a_new_version(client, kg, support_ontology):
    deprecated = support_ontology.replace("  - label: Ticket\n", "  - label: Ticket\n    deprecated: true\n")

    v2 = client.register_ontology(kg.name, deprecated)

    assert v2.number == 2


def test_an_ontology_can_be_registered_from_a_yaml_file(client, kg, tmp_path):
    path = tmp_path / "ontology.yaml"
    path.write_text(WITH_AGENT)

    v2 = client.register_ontology(kg.name, path)

    assert v2.ontology.node_type("Agent").label == "Agent"


def test_unknown_knowledge_graphs_and_versions_are_not_found(client, kg):
    with pytest.raises(stetiq.NotFoundError):
        client.list_ontology_versions("nope")
    with pytest.raises(stetiq.NotFoundError):
        client.register_ontology("nope", WITH_AGENT)
    with pytest.raises(stetiq.NotFoundError):
        client.get_ontology_version(kg.name, 2)
