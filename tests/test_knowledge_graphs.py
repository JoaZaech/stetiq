import sqlite3

import pytest

import stetiq
from stetiq.graph_source import GraphSourceScope


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


def test_knowledge_graphs_are_listed_by_name(client, support_ontology):
    assert client.list_knowledge_graphs() == []
    client.create_knowledge_graph("support", ontology=support_ontology)
    client.create_knowledge_graph("billing", ontology=support_ontology)

    assert [kg.name for kg in client.list_knowledge_graphs()] == ["billing", "support"]


def test_knowledge_graphs_persist_across_clients(client_factory, support_ontology):
    client_factory().create_knowledge_graph("customer-support-kg", ontology=support_ontology)

    versions = client_factory().list_ontology_versions("customer-support-kg")

    assert [v.number for v in versions] == [1]


EVOLVED_ONTOLOGY = """
node_types: [Customer, Ticket, Agent]
relationship_types: [OPENED]
patterns: [[Customer, OPENED, Ticket]]
"""


def test_listed_knowledge_graphs_carry_a_summary_of_their_state(client, support_ontology):
    client.create_knowledge_graph("support", ontology=support_ontology)
    client.register_ontology("support", EVOLVED_ONTOLOGY)
    client.bind_graph_source("support", GraphSourceScope(database="neo4j", label="KG_support"))
    run = client.start_run("support", ontology_version=1)
    run.fail()

    [kg] = client.list_knowledge_graphs()

    assert kg.contract_version == 1
    assert kg.latest_version == 2
    assert kg.last_run_status == "failed"
    assert kg.last_modified_at == client.get_run(run.id).ended_at


def test_a_new_knowledge_graph_summary_has_no_run_and_was_last_modified_at_creation(
    client, support_ontology
):
    created = client.create_knowledge_graph("support", ontology=support_ontology)

    [kg] = client.list_knowledge_graphs()

    assert kg.contract_version == 1
    assert kg.latest_version == 1
    assert kg.last_run_status is None
    # Creation ends by pointing the Contract Alias at v1.
    [initial_promotion] = client.list_promotions("support")
    assert kg.last_modified_at == initial_promotion.promoted_at
    assert kg.last_modified_at >= created.created_at


def test_the_summary_follows_the_contract_alias_when_it_is_promoted(client, support_ontology):
    client.create_knowledge_graph("support", ontology=support_ontology)
    client.register_ontology("support", EVOLVED_ONTOLOGY)

    promoted = client.set_alias("support", "production", 2)

    [kg] = client.list_knowledge_graphs()
    assert kg.contract_version == 2
    assert kg.last_modified_at == promoted.updated_at


def test_a_new_knowledge_graph_has_no_description(client, support_ontology):
    client.create_knowledge_graph("support", ontology=support_ontology)

    assert client.get_knowledge_graph("support").description is None


def test_the_description_is_set_and_read_back_as_markdown(client_factory, support_ontology):
    client = client_factory()
    client.create_knowledge_graph("support", ontology=support_ontology)

    updated = client.set_knowledge_graph_description("support", "Answers **support** questions.")

    assert updated.description == "Answers **support** questions."
    other = client_factory()
    assert other.get_knowledge_graph("support").description == "Answers **support** questions."
    [listed] = other.list_knowledge_graphs()
    assert listed.description == "Answers **support** questions."


def test_a_blank_description_clears_it(client, support_ontology):
    client.create_knowledge_graph("support", ontology=support_ontology)
    client.set_knowledge_graph_description("support", "Answers support questions.")

    client.set_knowledge_graph_description("support", "  \n")

    assert client.get_knowledge_graph("support").description is None


def test_describing_an_unknown_knowledge_graph_is_rejected(client):
    with pytest.raises(stetiq.NotFoundError):
        client.set_knowledge_graph_description("nope", "Anything.")


def test_a_database_from_before_descriptions_gains_the_column_on_startup(
    tmp_path, support_ontology
):
    url = f"sqlite:///{tmp_path / 'stetiq.db'}"
    stetiq.Client(url).create_knowledge_graph("support", ontology=support_ontology)
    with sqlite3.connect(tmp_path / "stetiq.db") as db:
        db.execute("ALTER TABLE knowledge_graphs DROP COLUMN description")

    client = stetiq.Client(url)
    client.set_knowledge_graph_description("support", "Answers support questions.")

    assert client.get_knowledge_graph("support").description == "Answers support questions."
