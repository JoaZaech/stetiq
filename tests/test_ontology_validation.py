import re

import pytest
import yaml

import stetiq

_BOUNDED = (
    "node_types: [WorkOrder, Machine]\nrelationship_types: [PERFORMED_ON]\npatterns:\n"
    "  - {{source: WorkOrder, relationship: PERFORMED_ON, target: Machine,"
    " cardinality: {cardinality}}}"
)

MALFORMED = {
    "not yaml": ("node_types: [Customer", "YAML"),
    "not a mapping": ("- Customer", "top level"),
    "no node types": ("relationship_types: []", "node_types"),
    "unknown top-level key": ("node_types: [Customer]\nnodes: [Ticket]", "nodes"),
    "node type without label": (
        "node_types:\n  - label: Customer\n  - description: nameless",
        "node_types[1]",
    ),
    "duplicate node type": ("node_types: [Customer, Customer]", "Customer"),
    "unknown key on a concept": (
        "node_types:\n  - label: Customer\n    propertes: []",
        "propertes",
    ),
    "unknown property type": (
        "node_types:\n  - label: Ticket\n    properties:\n      - {name: opened_at, type: TIMESTAMP}",
        "Ticket.opened_at",
    ),
    "property without name": (
        "node_types:\n  - label: Ticket\n    properties:\n      - {type: STRING}",
        "Ticket.properties[0]",
    ),
    "duplicate property": (
        "node_types:\n  - label: Ticket\n    properties:\n"
        "      - {name: title, type: STRING}\n      - {name: title, type: STRING}",
        "Ticket.title",
    ),
    "parent unknown node type": (
        "node_types:\n  - {label: Customer, parent: Party}",
        "Customer.parent",
    ),
    "hierarchy cycle": (
        "node_types:\n  - {label: A, parent: B}\n  - {label: B, parent: A}",
        "cycle",
    ),
    "parent on a relationship type": (
        "node_types: [Customer]\nrelationship_types:\n  - {label: KNOWS, parent: RELATED}",
        "parent",
    ),
    "constraint on unknown node type": (
        "node_types: [Customer]\nconstraints:\n"
        "  - {type: UNIQUENESS, node_type: Client, property_name: email}",
        "constraints[0]",
    ),
    "constraint on unknown property": (
        "node_types: [Customer]\nconstraints:\n"
        "  - {type: UNIQUENESS, node_type: Customer, property_name: email}",
        "Customer.email",
    ),
    "unknown constraint type": (
        "node_types:\n  - {label: Customer, properties: [{name: email, type: STRING}]}\nconstraints:\n"
        "  - {type: EXISTENCE, node_type: Customer, property_name: email}",
        "EXISTENCE",
    ),
    "duplicate constraint": (
        "node_types:\n  - {label: Customer, properties: [{name: email, type: STRING}]}\nconstraints:\n"
        "  - {type: UNIQUENESS, node_type: Customer, property_name: email}\n"
        "  - {type: UNIQUENESS, node_type: Customer, property_name: email}",
        "constraints[1]",
    ),
    "deprecated not a boolean": (
        "node_types:\n  - label: Customer\n    deprecated: maybe",
        "Customer.deprecated",
    ),
    "replacedBy unknown concept": (
        "node_types:\n  - label: Customer\n    replacedBy: Client",
        "Client",
    ),
    "both definition and description": (
        "node_types:\n  - label: Customer\n    definition: A buyer\n    description: A buyer",
        "Customer.definition: give either definition or description",
    ),
    "both definition and description on a property": (
        "node_types:\n  - label: Ticket\n    properties:\n"
        "      - {name: title, type: STRING, definition: a, description: a}",
        "Ticket.title.definition",
    ),
    "alternative label is another class's label": (
        "node_types:\n  - {label: Customer, alternativeLabels: [Client]}\n  - Client",
        "Customer.alternativeLabels: 'Client' is the label of another Concept in node_types",
    ),
    "alternative label is another relation's label": (
        "node_types: [A]\nrelationship_types:\n  - {label: OPENED, alternativeLabels: [RAISED]}\n"
        "  - RAISED",
        "OPENED.alternativeLabels",
    ),
    "alternative label is another attribute's name": (
        "node_types:\n  - label: Ticket\n    properties:\n"
        "      - {name: title, type: STRING, alternativeLabels: [subject]}\n"
        "      - {name: subject, type: STRING}",
        "Ticket.title.alternativeLabels",
    ),
    "empty alternative label": (
        "node_types:\n  - {label: Customer, alternativeLabels: ['']}",
        "Customer.alternativeLabels",
    ),
    "duplicate alternative label": (
        "node_types:\n  - {label: Customer, alternativeLabels: [Client, Client]}",
        "Customer.alternativeLabels: Alternative Label 'Client' is given more than once",
    ),
    "duplicate alternative label on a property": (
        "node_types:\n  - label: Ticket\n    properties:\n"
        "      - {name: title, type: STRING, alternativeLabels: [subject, subject]}",
        "Ticket.title.alternativeLabels",
    ),
    "alternative labels not a list": (
        "node_types:\n  - {label: Customer, alternativeLabels: Client}",
        "Customer.alternativeLabels",
    ),
    "attribute replaced by an attribute on another owner": (
        "node_types:\n  - label: Ticket\n    properties:\n"
        "      - {name: priority, type: FLOAT, replacedBy: urgency}\n"
        "  - label: Case\n    properties:\n      - {name: urgency, type: FLOAT}",
        "Ticket.priority.replacedBy: 'urgency' is not another Concept declared in Ticket's properties",
    ),
    "attribute replaced by itself": (
        "node_types:\n  - label: Ticket\n    properties:\n"
        "      - {name: priority, type: FLOAT, replacedBy: priority}",
        "Ticket.priority.replacedBy",
    ),
    "attribute deprecated not a boolean": (
        "node_types:\n  - label: Ticket\n    properties:\n"
        "      - {name: priority, type: FLOAT, deprecated: soon}",
        "Ticket.priority.deprecated",
    ),
    "deprecation reason not a string": (
        "node_types:\n  - {label: Customer, deprecated: true, deprecationReason: [a]}",
        "Customer.deprecationReason",
    ),
    "deprecation reason without a deprecation": (
        "node_types:\n  - {label: Customer, deprecationReason: Unused}",
        "Customer.deprecationReason: a Deprecation reason needs deprecated: true or a replacedBy",
    ),
    "attribute deprecation reason without a deprecation": (
        "node_types:\n  - label: Ticket\n    properties:\n"
        "      - {name: priority, type: FLOAT, deprecationReason: Unused}",
        "Ticket.priority.deprecationReason",
    ),
    "pattern with undeclared node type": (
        "node_types: [Customer]\nrelationship_types: [OPENED]\npatterns:\n  - [Customer, OPENED, Ticket]",
        "Ticket",
    ),
    "pattern with undeclared relationship type": (
        "node_types: [Customer, Ticket]\npatterns:\n  - [Customer, OPENED, Ticket]",
        "OPENED",
    ),
    "pattern not a triple": (
        "node_types: [Customer]\nrelationship_types: [KNOWS]\npatterns:\n  - [Customer, KNOWS]",
        "patterns[0]",
    ),
    "negative cardinality bound": (
        _BOUNDED.format(cardinality="{in: {min: -1}}"),
        "patterns[0].cardinality.in.min",
    ),
    "cardinality min greater than max": (
        _BOUNDED.format(cardinality="{out: {min: 2, max: 1}}"),
        "patterns[0].cardinality.out",
    ),
    "cardinality bound not an integer": (
        _BOUNDED.format(cardinality="{out: {max: many}}"),
        "patterns[0].cardinality.out.max",
    ),
    "unknown cardinality direction": (
        _BOUNDED.format(cardinality="{both: {max: 1}}"),
        "both",
    ),
}


@pytest.mark.parametrize(
    ("yaml_text", "offending_element"), MALFORMED.values(), ids=MALFORMED.keys()
)
def test_malformed_ontology_is_rejected_naming_the_offending_element(
    client, yaml_text, offending_element
):
    with pytest.raises(stetiq.OntologyValidationError, match=re.escape(offending_element)):
        client.create_knowledge_graph("customer-support-kg", ontology=yaml_text)


def test_registering_a_malformed_ontology_creates_no_version(client, support_ontology):
    client.create_knowledge_graph("customer-support-kg", ontology=support_ontology)

    with pytest.raises(stetiq.OntologyValidationError):
        client.register_ontology("customer-support-kg", "node_types: [Customer, Customer]")

    assert [v.number for v in client.list_ontology_versions("customer-support-kg")] == [1]


def test_patterns_may_be_given_in_neo4j_graphrag_mapping_form(client):
    client.create_knowledge_graph(
        "customer-support-kg",
        ontology="node_types: [Customer, Ticket]\nrelationship_types: [OPENED]\n"
        "patterns:\n  - {source: Customer, relationship: OPENED, target: Ticket}",
    )

    fetched = yaml.safe_load(client.get_ontology_yaml("customer-support-kg", 1))

    assert fetched["patterns"] == [["Customer", "OPENED", "Ticket"]]


def test_node_and_relationship_types_may_be_given_as_bare_labels(client):
    client.create_knowledge_graph(
        "customer-support-kg",
        ontology="node_types: [Customer, Ticket]\nrelationship_types: [OPENED]\n"
        "patterns:\n  - [Customer, OPENED, Ticket]",
    )

    ontology = client.get_ontology_version("customer-support-kg", 1).ontology

    assert [n.label for n in ontology.node_types] == ["Customer", "Ticket"]
    assert [r.label for r in ontology.relationship_types] == ["OPENED"]
