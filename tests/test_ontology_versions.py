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
            {
                "label": "Customer",
                "properties": [{"name": "name", "type": "STRING", "required": True}],
            },
            {
                "label": "Ticket",
                "definition": "A support request",
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

    assert {"label": "Customer", "deprecated": True, "replacedBy": "Client"} in fetched[
        "node_types"
    ]
    assert {"label": "OPENED", "deprecated": True} in fetched["relationship_types"]
    assert {"label": "RAISED", "replacedBy": "OPENED"} in fetched["relationship_types"]
    assert ontology.node_type("Customer").replaced_by == "Client"
    assert ontology.relationship_type("OPENED").deprecated is True


def test_node_type_hierarchy_round_trips_through_fetch(client, kg):
    v2 = client.register_ontology(
        kg.name, "node_types:\n  - Party\n  - {label: Customer, parent: Party}\n"
    )

    fetched = yaml.safe_load(client.get_ontology_yaml(kg.name, v2.number))

    assert {"label": "Customer", "parent": "Party"} in fetched["node_types"]
    assert (
        client.get_ontology_version(kg.name, v2.number).ontology.node_type("Customer").parent
        == "Party"
    )
    again = client.register_ontology(kg.name, client.get_ontology_yaml(kg.name, v2.number))
    assert (again.number, again.content_hash) == (v2.number, v2.content_hash)


def test_constraints_round_trip_through_fetch(client, kg, support_ontology):
    constrained = support_ontology + (
        "constraints:\n  - {type: UNIQUENESS, node_type: Customer, property_name: name}\n"
    )
    v2 = client.register_ontology(kg.name, constrained)

    fetched = yaml.safe_load(client.get_ontology_yaml(kg.name, v2.number))

    assert fetched["constraints"] == [
        {"type": "UNIQUENESS", "node_type": "Customer", "property_name": "name"}
    ]
    again = client.register_ontology(kg.name, client.get_ontology_yaml(kg.name, v2.number))
    assert (again.number, again.content_hash) == (2, v2.content_hash)


def test_cardinality_round_trips_through_fetch(client, kg):
    v2 = client.register_ontology(
        kg.name,
        """
node_types: [WorkOrder, Machine]
relationship_types: [PERFORMED_ON]
patterns:
  - source: WorkOrder
    relationship: PERFORMED_ON
    target: Machine
    cardinality: {out: {min: 1, max: 1}, in: {min: 0}}
""",
    )

    fetched = yaml.safe_load(client.get_ontology_yaml(kg.name, v2.number))
    (pattern,) = client.get_ontology_version(kg.name, v2.number).ontology.patterns

    assert fetched["patterns"] == [
        {
            "source": "WorkOrder",
            "relationship": "PERFORMED_ON",
            "target": "Machine",
            "cardinality": {"out": {"min": 1, "max": 1}, "in": {"min": 0}},
        }
    ]
    assert (pattern.min_out, pattern.max_out, pattern.min_in, pattern.max_in) == (1, 1, 0, None)
    again = client.register_ontology(kg.name, client.get_ontology_yaml(kg.name, v2.number))
    assert (again.number, again.content_hash) == (v2.number, v2.content_hash)


def test_a_cardinality_is_part_of_the_ontology_version(client, kg):
    plain = "node_types: [A, B]\nrelationship_types: [R]\npatterns: [[A, R, B]]\n"
    bounded = (
        "node_types: [A, B]\nrelationship_types: [R]\npatterns:\n"
        "  - {source: A, relationship: R, target: B, cardinality: {in: {max: 3}}}\n"
    )

    v_plain = client.register_ontology(kg.name, plain)
    v_bounded = client.register_ontology(kg.name, bounded)

    assert v_bounded.number == v_plain.number + 1
    assert v_bounded.content_hash != v_plain.content_hash
    assert yaml.safe_load(client.get_ontology_yaml(kg.name, v_plain.number))["patterns"] == [
        ["A", "R", "B"]
    ]


def test_deprecating_a_concept_creates_a_new_version(client, kg, support_ontology):
    deprecated = support_ontology.replace(
        "  - label: Ticket\n", "  - label: Ticket\n    deprecated: true\n"
    )

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


WITH_DEFINITIONS = """
node_types:
  - label: WorkOrder
    definition: A request to perform maintenance on one Machine
    alternativeLabels: [WO, Job]
    properties:
      - name: status
        type: STRING
        definition: Where the work order is in its lifecycle
        alternativeLabels: [state]
  - Machine
relationship_types:
  - label: PERFORMED_ON
    definition: The Machine a work order is carried out on
    alternativeLabels: [TARGETS]
patterns:
  - [WorkOrder, PERFORMED_ON, Machine]
"""


def test_definitions_and_alternative_labels_round_trip_through_registration(client, kg):
    v2 = client.register_ontology(kg.name, WITH_DEFINITIONS)

    ontology = client.get_ontology_version(kg.name, v2.number).ontology
    work_order = ontology.node_type("WorkOrder")
    performed_on = ontology.relationship_type("PERFORMED_ON")
    [status] = work_order.properties

    assert work_order.definition == "A request to perform maintenance on one Machine"
    assert work_order.alternative_labels == ("WO", "Job")
    assert ontology.node_type("Machine").alternative_labels == ()
    assert status.definition == "Where the work order is in its lifecycle"
    assert status.alternative_labels == ("state",)
    assert performed_on.definition == "The Machine a work order is carried out on"
    assert performed_on.alternative_labels == ("TARGETS",)


def test_fetched_yaml_spells_definitions_and_alternative_labels_as_written(client, kg):
    v2 = client.register_ontology(kg.name, WITH_DEFINITIONS)

    fetched = yaml.safe_load(client.get_ontology_yaml(kg.name, v2.number))
    again = client.register_ontology(kg.name, client.get_ontology_yaml(kg.name, v2.number))

    assert {
        "label": "WorkOrder",
        "definition": "A request to perform maintenance on one Machine",
        "alternativeLabels": ["WO", "Job"],
        "properties": [
            {
                "name": "status",
                "type": "STRING",
                "definition": "Where the work order is in its lifecycle",
                "alternativeLabels": ["state"],
            }
        ],
    } in fetched["node_types"]
    assert (again.number, again.content_hash) == (v2.number, v2.content_hash)


def test_description_is_accepted_as_the_older_spelling_of_definition(client, kg):
    v2 = client.register_ontology(
        kg.name,
        WITH_DEFINITIONS.replace("definition:", "description:"),
    )

    ontology = v2.ontology
    assert ontology.node_type("WorkOrder").definition == (
        "A request to perform maintenance on one Machine"
    )
    assert ontology.node_type("WorkOrder").properties[0].definition == (
        "Where the work order is in its lifecycle"
    )
    again = client.register_ontology(kg.name, WITH_DEFINITIONS)
    assert (again.number, again.content_hash) == (v2.number, v2.content_hash)


def test_an_unchanged_ontology_written_with_definition_deduplicates_to_its_older_version(
    client, kg
):
    # v1 was registered with `description: A support request`; the golden hash test
    # pins its hash, which therefore survives the new spelling.
    again = client.register_ontology(
        kg.name, SUPPORT_ONTOLOGY_REORDERED.replace("description:", "definition:")
    )

    assert again.number == 1


WITH_DEPRECATIONS = """
node_types:
  - label: WorkOrder
    properties:
      - {name: state, type: STRING, replacedBy: status, deprecationReason: Renamed for the MES}
      - {name: status, type: STRING}
      - {name: legacy_id, type: STRING, deprecated: true}
  - {label: Job, replacedBy: WorkOrder, deprecationReason: Merged into WorkOrder}
  - Machine
relationship_types:
  - {label: PERFORMED_ON, deprecated: true, deprecationReason: Use RUNS_ON}
  - RUNS_ON
patterns:
  - [WorkOrder, RUNS_ON, Machine]
"""


def test_attribute_deprecations_and_deprecation_reasons_round_trip_through_registration(client, kg):
    v2 = client.register_ontology(kg.name, WITH_DEPRECATIONS)

    ontology = client.get_ontology_version(kg.name, v2.number).ontology
    properties = {p.name: p for p in ontology.node_type("WorkOrder").properties}
    state, status, legacy_id = properties["state"], properties["status"], properties["legacy_id"]

    assert (state.deprecated, state.replaced_by, state.deprecation_reason) == (
        False,
        "status",
        "Renamed for the MES",
    )
    assert (legacy_id.deprecated, legacy_id.replaced_by, legacy_id.deprecation_reason) == (
        True,
        None,
        None,
    )
    assert (status.deprecated, status.replaced_by) == (False, None)
    assert ontology.node_type("Job").deprecation_reason == "Merged into WorkOrder"
    assert ontology.node_type("Machine").deprecation_reason is None
    assert ontology.relationship_type("PERFORMED_ON").deprecation_reason == "Use RUNS_ON"


def test_fetched_yaml_spells_attribute_deprecations_and_reasons_as_written(client, kg):
    v2 = client.register_ontology(kg.name, WITH_DEPRECATIONS)

    fetched = yaml.safe_load(client.get_ontology_yaml(kg.name, v2.number))
    again = client.register_ontology(kg.name, client.get_ontology_yaml(kg.name, v2.number))

    work_order = next(n for n in fetched["node_types"] if n["label"] == "WorkOrder")
    assert work_order["properties"] == [
        {"name": "legacy_id", "type": "STRING", "deprecated": True},
        {
            "name": "state",
            "type": "STRING",
            "replacedBy": "status",
            "deprecationReason": "Renamed for the MES",
        },
        {"name": "status", "type": "STRING"},
    ]
    assert {
        "label": "Job",
        "replacedBy": "WorkOrder",
        "deprecationReason": "Merged into WorkOrder",
    } in fetched["node_types"]
    assert (again.number, again.content_hash) == (v2.number, v2.content_hash)
