"""Ontology Diff: every Concept change between two Ontology Versions, classified."""

import pytest

from stetiq import OntologyDiff
from stetiq.ontology.model import Pattern

KG = "customer-support-kg"

BASE = """
node_types:
  - label: Customer
    properties:
      - {name: name, type: STRING, required: true}
  - label: Ticket
    properties:
      - {name: opened_at, type: DATE}
      - {name: priority, type: FLOAT}
  - Agent
relationship_types: [OPENED, HANDLES]
patterns:
  - [Customer, OPENED, Ticket]
  - [Agent, HANDLES, Ticket]
"""


@pytest.fixture
def diff(client):
    """Register BASE as v1, the evolved YAML as v2, and diff v1 -> v2."""
    client.create_knowledge_graph(KG, ontology=BASE)

    def _diff(evolved: str) -> OntologyDiff:
        version = client.register_ontology(KG, evolved)
        return client.diff_ontology_versions(KG, 1, version.number)

    return _diff


def summary(d: OntologyDiff) -> list[tuple[str, str, str]]:
    return [(c.concept, c.kind, c.classification) for c in d.changes]


def attributes(d: OntologyDiff) -> list[tuple[str | None, str | None, str | None]]:
    """Each change's attribute as the Diff states it: owner, owner kind, attribute name."""
    return [(c.owner, c.owner_kind, c.attribute) for c in d.changes]


def concerns_the_concept_itself(d: OntologyDiff) -> bool:
    """Whether every change is to a node or relationship type itself: no attribute, no Pattern."""
    return all(
        (c.owner, c.owner_kind, c.attribute, c.required, c.pattern) == (None,) * 5
        for c in d.changes
    )


def test_adding_a_concept_is_additive(diff):
    d = diff(BASE.replace("  - Agent", "  - Agent\n  - Product"))

    assert summary(d) == [("Product", "added", "additive")]
    assert concerns_the_concept_itself(d)
    assert d.classification == "additive"
    assert not d.is_breaking


def test_removing_a_concept_is_breaking(diff):
    d = diff(
        BASE.replace("[OPENED, HANDLES]", "[OPENED, ASSIGNED]").replace(
            "HANDLES, Ticket]", "ASSIGNED, Ticket]"
        )
    )

    assert summary(d) == [("ASSIGNED", "added", "additive"), ("HANDLES", "removed", "breaking")]
    assert concerns_the_concept_itself(d)
    assert d.classification == "breaking"
    assert d.is_breaking
    assert [c.concept for c in d.breaking] == ["HANDLES"]


def test_narrowing_a_relations_endpoint_patterns_is_breaking(diff):
    d = diff(
        BASE.replace(
            "  - [Agent, HANDLES, Ticket]",
            "  - [Agent, HANDLES, Ticket]\n  - [Agent, OPENED, Ticket]",
        ).replace("  - [Customer, OPENED, Ticket]\n", "")
    )

    assert summary(d) == [("OPENED", "changed", "additive"), ("OPENED", "changed", "breaking")]
    widened, narrowed = d.changes
    assert widened.pattern == Pattern("Agent", "OPENED", "Ticket")
    assert narrowed.pattern == Pattern("Customer", "OPENED", "Ticket")
    assert (widened.owner, widened.attribute, widened.required) == (None, None, None)


def test_narrowing_a_propertys_type_is_breaking(diff):
    d = diff(BASE.replace("{name: priority, type: FLOAT}", "{name: priority, type: INTEGER}"))

    assert summary(d) == [("Ticket.priority", "changed", "breaking")]
    assert d.changes[0].concept_kind == "property"
    assert attributes(d) == [("Ticket", "node_type", "priority")]
    assert "FLOAT -> INTEGER" in d.changes[0].detail


def test_a_relations_attribute_change_names_the_relation_as_its_owner(client):
    # A node type and a relationship type share the label Ticket: only the relation's attribute changes.
    node = "node_types: [{label: Ticket, properties: [{name: at, type: DATE}]}]\n"
    d = client.diff_ontologies(
        node + "relationship_types: [{label: Ticket, properties: [{name: at, type: DATE}]}]\n",
        node + "relationship_types: [{label: Ticket, properties: [{name: at, type: STRING}]}]\n",
    )

    assert summary(d) == [("Ticket.at", "changed", "breaking")]
    assert attributes(d) == [("Ticket", "relationship_type", "at")]


def test_widening_a_propertys_type_is_additive(client):
    d = client.diff_ontologies(
        BASE.replace("{name: priority, type: FLOAT}", "{name: priority, type: INTEGER}"), BASE
    )

    assert summary(d) == [("Ticket.priority", "changed", "additive")]


def test_adding_an_optional_property_is_additive_but_a_required_one_is_breaking(diff):
    d = diff(
        BASE.replace(
            "      - {name: priority, type: FLOAT}",
            "      - {name: priority, type: FLOAT}\n"
            "      - {name: channel, type: STRING}\n"
            "      - {name: status, type: STRING, required: true}",
        )
    )

    assert summary(d) == [
        ("Ticket.channel", "added", "additive"),
        ("Ticket.status", "added", "breaking"),
    ]
    assert attributes(d) == [("Ticket", "node_type", "channel"), ("Ticket", "node_type", "status")]
    assert [c.required for c in d.changes] == [False, True]


def test_removing_a_property_is_breaking(diff):
    d = diff(BASE.replace("      - {name: priority, type: FLOAT}\n", ""))

    assert summary(d) == [("Ticket.priority", "removed", "breaking")]
    assert attributes(d) == [("Ticket", "node_type", "priority")]
    assert d.changes[0].required is None


def test_making_a_property_required_is_breaking_and_optional_is_additive(diff):
    d = diff(
        BASE.replace(
            "{name: name, type: STRING, required: true}", "{name: name, type: STRING}"
        ).replace("{name: opened_at, type: DATE}", "{name: opened_at, type: DATE, required: true}")
    )

    assert summary(d) == [
        ("Customer.name", "changed", "additive"),
        ("Ticket.opened_at", "changed", "breaking"),
    ]
    assert attributes(d) == [
        ("Customer", "node_type", "name"),
        ("Ticket", "node_type", "opened_at"),
    ]


def test_marking_a_concept_deprecated_is_deprecating(diff):
    d = diff(BASE.replace("  - Agent", "  - {label: Agent, deprecated: true}"))

    assert summary(d) == [("Agent", "deprecated", "deprecating")]
    assert concerns_the_concept_itself(d)
    assert d.classification == "deprecating"
    assert not d.is_breaking


def test_a_rename_declared_via_replaced_by_is_deprecating(diff):
    d = diff(
        BASE.replace(
            "[OPENED, HANDLES]", "[OPENED, {label: HANDLES, replacedBy: RESOLVES}, RESOLVES]"
        )
        + "  - [Agent, RESOLVES, Ticket]\n"
    )

    assert summary(d) == [
        ("HANDLES", "deprecated", "deprecating"),
        ("RESOLVES", "added", "additive"),
    ]
    assert "replaced by RESOLVES" in d.changes[0].detail
    assert d.classification == "deprecating"
    assert concerns_the_concept_itself(d)


def test_undeprecating_is_additive_and_changing_a_replacement_is_deprecating(client):
    deprecated = "node_types: [{label: Agent, deprecated: true}]\n"
    replaced = "node_types: [{label: Agent, replacedBy: Staff}, Staff, Worker]\n"
    retargeted = "node_types: [{label: Agent, replacedBy: Worker}, Staff, Worker]\n"

    undeprecated = client.diff_ontologies(deprecated, "node_types: [Agent]\n")
    changed = client.diff_ontologies(replaced, retargeted)

    assert summary(undeprecated) == [("Agent", "changed", "additive")]
    assert summary(changed) == [("Agent", "deprecated", "deprecating")]
    assert concerns_the_concept_itself(undeprecated)
    assert concerns_the_concept_itself(changed)


def test_an_undeclared_rename_is_a_removal_plus_an_addition(diff):
    d = diff(BASE.replace("HANDLES", "RESOLVES"))

    assert summary(d) == [("HANDLES", "removed", "breaking"), ("RESOLVES", "added", "additive")]
    assert d.is_breaking


def test_diffing_a_version_with_itself_has_no_changes(client):
    client.create_knowledge_graph(KG, ontology=BASE)

    d = client.diff_ontology_versions(KG, 1, 1)

    assert d.changes == ()
    assert d.classification is None
    assert not d.is_breaking


def test_diffing_an_unknown_version_is_not_found(client):
    import stetiq

    client.create_knowledge_graph(KG, ontology=BASE)

    with pytest.raises(stetiq.NotFoundError):
        client.diff_ontology_versions(KG, 1, 7)


def test_changing_only_a_description_is_cosmetic(diff):
    d = diff(
        BASE.replace(
            "  - label: Ticket\n", "  - label: Ticket\n    description: A support request\n"
        ).replace(
            "{name: opened_at, type: DATE}",
            "{name: opened_at, type: DATE, description: When it was opened}",
        )
    )

    assert summary(d) == [
        ("Ticket", "changed", "cosmetic"),
        ("Ticket.opened_at", "changed", "cosmetic"),
    ]
    assert attributes(d) == [(None, None, None), ("Ticket", "node_type", "opened_at")]
    assert d.classification == "cosmetic"
    assert d.cosmetic == d.changes


def test_a_cosmetic_change_ranks_below_an_additive_one(diff):
    d = diff(
        BASE.replace(
            "  - label: Ticket\n", "  - label: Ticket\n    description: A support request\n"
        ).replace("  - Agent", "  - Agent\n  - Product")
    )

    assert summary(d) == [("Product", "added", "additive"), ("Ticket", "changed", "cosmetic")]
    assert d.classification == "additive"


def test_giving_a_root_node_type_a_parent_is_additive_but_moving_it_is_breaking(client):
    flat = "node_types: [Party, Organisation, Customer]\n"
    under_party = "node_types: [Party, Organisation, {label: Customer, parent: Party}]\n"
    moved = "node_types: [Party, Organisation, {label: Customer, parent: Organisation}]\n"

    assert summary(client.diff_ontologies(flat, under_party)) == [
        ("Customer", "changed", "additive")
    ]
    assert summary(client.diff_ontologies(under_party, moved)) == [
        ("Customer", "changed", "breaking")
    ]
    assert summary(client.diff_ontologies(under_party, flat)) == [
        ("Customer", "changed", "breaking")
    ]
    assert concerns_the_concept_itself(client.diff_ontologies(under_party, moved))


def test_adding_a_constraint_is_breaking_and_dropping_one_is_additive(client):
    plain = "node_types:\n  - {label: Customer, properties: [{name: email, type: STRING}]}\n"
    unique = (
        plain + "constraints:\n  - {type: UNIQUENESS, node_type: Customer, property_name: email}\n"
    )

    assert summary(client.diff_ontologies(plain, unique)) == [
        ("Customer.email", "changed", "breaking")
    ]
    assert attributes(client.diff_ontologies(plain, unique)) == [("Customer", "node_type", "email")]
    assert summary(client.diff_ontologies(unique, plain)) == [
        ("Customer.email", "changed", "additive")
    ]


def _with_node_type(label: str) -> str:
    return BASE.replace("  - Agent\n", f"  - Agent\n  - {label}\n")


def test_a_bare_diff_compares_the_latest_candidate_with_the_contract(client):
    client.create_knowledge_graph(KG, ontology=BASE)  # v1, production
    client.register_ontology(KG, _with_node_type("Team"))  # v2, a Candidate
    client.register_ontology(KG, _with_node_type("Shift"))  # v3
    client.set_alias(KG, "staging", 3)  # v3 is no longer a Candidate

    d = client.diff_ontology_versions(KG)

    assert [(c.kind, c.concept) for c in d.changes] == [("added", "Team")]


def test_a_bare_diff_without_candidates_compares_the_latest_version(client):
    client.create_knowledge_graph(KG, ontology=BASE)
    client.register_ontology(KG, _with_node_type("Team"))
    client.set_alias(KG, "staging", 2)

    d = client.diff_ontology_versions(KG)

    assert [(c.kind, c.concept) for c in d.changes] == [("added", "Team")]
