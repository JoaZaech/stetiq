"""Aliases, the Contract Alias and Promotion, through the SDK."""

import pytest

import stetiq

EVOLVED_ONTOLOGY = """
node_types: [Customer, Ticket, Agent]
relationship_types: [OPENED]
patterns: [[Customer, OPENED, Ticket]]
"""


@pytest.fixture
def support_kg(client, support_ontology):
    client.create_knowledge_graph("support", ontology=support_ontology)
    client.register_ontology("support", EVOLVED_ONTOLOGY)  # Ontology Version 2
    return "support"


def test_an_alias_can_be_created_and_its_ontology_version_fetched(client, support_kg):
    alias = client.set_alias(support_kg, "staging", 2)

    assert (alias.knowledge_graph, alias.name, alias.version) == ("support", "staging", 2)
    fetched = client.get_ontology_version_by_alias(support_kg, "staging")
    assert fetched.number == 2
    assert fetched.ontology.node_type("Agent") is not None


def test_aliases_are_listed_per_knowledge_graph_by_name(client, support_kg, support_ontology):
    client.create_knowledge_graph("other", ontology=support_ontology)
    client.set_alias(support_kg, "staging", 2)
    client.set_alias(support_kg, "canary", 1)
    client.set_alias("other", "staging", 1)

    listed = client.list_aliases(support_kg)

    assert [(a.name, a.version) for a in listed if a.name != "production"] == [
        ("canary", 1),
        ("staging", 2),
    ]


def test_moving_an_alias_back_to_an_earlier_version_is_a_rollback(client, support_kg):
    client.set_alias(support_kg, "staging", 1)
    client.set_alias(support_kg, "staging", 2)

    client.set_alias(support_kg, "staging", 1)

    assert client.get_alias(support_kg, "staging").version == 1
    assert client.get_ontology_version_by_alias(support_kg, "staging").number == 1


def test_an_alias_cannot_point_to_an_unknown_ontology_version(client, support_kg):
    with pytest.raises(stetiq.NotFoundError):
        client.set_alias(support_kg, "staging", 9)

    with pytest.raises(stetiq.NotFoundError):
        client.get_alias(support_kg, "staging")


def test_an_unknown_alias_cannot_be_fetched(client, support_kg):
    with pytest.raises(stetiq.NotFoundError):
        client.get_ontology_version_by_alias(support_kg, "nope")


@pytest.mark.parametrize("name", ["", "has space", "a/b"])
def test_alias_names_are_validated(client, support_kg, name):
    with pytest.raises(stetiq.InvalidAliasNameError) as raised:
        client.set_alias(support_kg, name, 1)

    assert str(raised.value) == f"Alias name {name!r} must be letters, digits, '_', '-' or '.'"


def test_aliases_persist_across_clients(client_factory, support_ontology):
    client_factory().create_knowledge_graph("support", ontology=support_ontology)
    client_factory().set_alias("support", "staging", 1)

    assert client_factory().get_alias("support", "staging").version == 1


def test_a_new_knowledge_graph_has_production_as_contract_alias_on_its_declared_ontology(
    client, support_ontology
):
    client.create_knowledge_graph("support", ontology=support_ontology)

    assert client.get_contract_alias("support") == "production"
    assert client.get_alias("support", "production").version == 1
    assert client.get_contract_version("support").number == 1


def test_another_alias_can_be_designated_contract_alias(client, support_kg):
    client.set_alias(support_kg, "live", 2)

    client.set_contract_alias(support_kg, "live")

    assert client.get_contract_alias(support_kg) == "live"
    assert client.get_contract_version(support_kg).number == 2


def test_only_an_existing_alias_can_be_contract_alias(client, support_kg):
    with pytest.raises(stetiq.NotFoundError):
        client.set_contract_alias(support_kg, "nope")

    assert client.get_contract_alias(support_kg) == "production"


def test_a_run_without_an_explicit_version_consumes_the_contract_alias_version(client, support_kg):
    client.bind_graph_source(support_kg, stetiq.GraphSourceScope(database="neo4j"))
    client.set_alias(support_kg, "production", 2)

    run = client.start_run(support_kg)

    assert run.ontology_version == 2
    assert run.declared_ontology == client.get_ontology_version(support_kg, 2).ontology
    assert client.get_run(run.id).ontology_version == 2


def test_a_run_follows_the_designated_contract_alias(client, support_kg):
    client.bind_graph_source(support_kg, stetiq.GraphSourceScope(database="neo4j"))
    client.set_alias(support_kg, "live", 2)
    client.set_contract_alias(support_kg, "live")

    assert client.start_run(support_kg).ontology_version == 2


def test_a_run_can_consume_another_alias_instead_of_the_contract(client, support_kg):
    client.bind_graph_source(support_kg, stetiq.GraphSourceScope(database="neo4j"))
    client.set_alias(support_kg, "staging", 2)

    assert client.start_run(support_kg, alias="staging").ontology_version == 2
    assert client.start_run(support_kg).ontology_version == 1


def test_a_run_takes_a_version_or_an_alias_not_both(client, support_kg):
    client.bind_graph_source(support_kg, stetiq.GraphSourceScope(database="neo4j"))

    with pytest.raises(stetiq.ConflictingArgumentsError) as raised:
        client.start_run(support_kg, ontology_version=1, alias="production")

    assert str(raised.value) == "A run consumes an ontology_version or an alias, not both"
    assert isinstance(raised.value, ValueError)  # as before it was a StetiqError
    assert client.list_runs(support_kg) == []


def test_every_alias_move_is_audit_logged_with_actor_time_and_versions(
    client_factory, support_ontology
):
    from datetime import UTC, datetime

    ada = client_factory(actor="ada")
    ada.create_knowledge_graph("support", ontology=support_ontology)
    ada.register_ontology("support", EVOLVED_ONTOLOGY)
    before = datetime.now(UTC)

    ada.set_alias("support", "production", 2)  # Promotion
    ada.set_alias("support", "production", 1)  # rollback
    ada.set_alias("support", "staging", 2)  # creation

    log = client_factory().list_promotions("support")
    assert [(p.alias, p.from_version, p.to_version, p.actor) for p in log] == [
        ("production", None, 1, "stetiq"),  # the Contract Alias set on creation
        ("production", 1, 2, "ada"),
        ("production", 2, 1, "ada"),
        ("staging", None, 2, "ada"),
    ]
    assert all(p.promoted_at >= before for p in log[1:])
    assert all(p.gate_result is None for p in log)  # no Gates yet


def test_pointing_an_alias_where_it_already_points_logs_nothing(client, support_kg):
    client.set_alias(support_kg, "production", 1)

    assert len(client.list_promotions(support_kg)) == 1


def test_the_actor_defaults_to_the_stetiq_actor_environment_variable(
    client_factory, support_kg, monkeypatch
):
    monkeypatch.setenv("STETIQ_ACTOR", "ci-bot")

    client_factory().set_alias(support_kg, "production", 2)
    client_factory(actor="ada").set_alias(support_kg, "production", 1)

    assert [p.actor for p in client_factory().list_promotions(support_kg)[-2:]] == ["ci-bot", "ada"]


def test_the_ontology_diff_defaults_to_the_contract_alias_version_as_base(client, support_kg):
    client.register_ontology(support_kg, EVOLVED_ONTOLOGY.replace("Agent", "Agent, Team"))  # v3

    against_contract = client.diff_ontology_versions(support_kg, target=2)
    no_arguments = client.diff_ontology_versions(support_kg)  # contract (v1) -> latest (v3)

    assert any(c.concept == "Agent" and c.kind == "added" for c in against_contract.changes)
    assert not any(c.concept == "Team" for c in against_contract.changes)
    assert any(c.concept == "Team" and c.kind == "added" for c in no_arguments.changes)


def test_the_default_diff_base_follows_a_promotion(client, support_kg):
    client.set_alias(support_kg, "production", 2)

    assert client.diff_ontology_versions(support_kg, target=2).changes == ()
