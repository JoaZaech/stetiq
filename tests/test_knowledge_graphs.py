import pytest

import stetiq


def test_creating_a_knowledge_graph_registers_its_declared_ontology_as_first_version(
    client, support_ontology
):
    kg = client.create_knowledge_graph("customer-support-kg", ontology=support_ontology)

    versions = client.list_ontology_versions("customer-support-kg")

    assert kg.name == "customer-support-kg"
    assert [v.number for v in versions] == [1]
    assert versions[0].origin == "registered"


def test_creating_a_knowledge_graph_without_a_declared_ontology_is_rejected(client):
    with pytest.raises(stetiq.MissingDeclaredOntologyError):
        client.create_knowledge_graph("customer-support-kg")

    with pytest.raises(stetiq.NotFoundError):
        client.get_knowledge_graph("customer-support-kg")


def test_knowledge_graph_names_are_unique(client, support_ontology):
    client.create_knowledge_graph("customer-support-kg", ontology=support_ontology)

    with pytest.raises(stetiq.KnowledgeGraphAlreadyExistsError):
        client.create_knowledge_graph("customer-support-kg", ontology=support_ontology)


def test_knowledge_graph_with_malformed_ontology_is_not_created(client):
    with pytest.raises(stetiq.OntologyValidationError):
        client.create_knowledge_graph("customer-support-kg", ontology="node_types: 42")

    with pytest.raises(stetiq.NotFoundError):
        client.get_knowledge_graph("customer-support-kg")


def test_knowledge_graphs_persist_across_clients(tmp_path, support_ontology):
    uri = f"sqlite:///{tmp_path / 'stetiq.db'}"
    stetiq.Client(uri).create_knowledge_graph("customer-support-kg", ontology=support_ontology)

    versions = stetiq.Client(uri).list_ontology_versions("customer-support-kg")

    assert [v.number for v in versions] == [1]
