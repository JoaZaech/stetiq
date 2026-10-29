"""Ontology Diff: every Concept change between two Ontology Versions, classified."""

import pytest

from stetiq import OntologyDiff

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


def test_adding_a_concept_is_additive(diff):
    d = diff(BASE.replace("  - Agent", "  - Agent\n  - Product"))

    assert summary(d) == [("Product", "added", "additive")]
    assert d.classification == "additive"
    assert not d.is_breaking


def test_removing_a_concept_is_breaking(diff):
    d = diff(BASE.replace("[OPENED, HANDLES]", "[OPENED, ASSIGNED]").replace("HANDLES, Ticket]", "ASSIGNED, Ticket]"))

    assert summary(d) == [("ASSIGNED", "added", "additive"), ("HANDLES", "removed", "breaking")]
    assert d.classification == "breaking"
    assert d.is_breaking
    assert [c.concept for c in d.breaking] == ["HANDLES"]


def test_narrowing_a_relations_endpoint_patterns_is_breaking(diff):
    d = diff(BASE.replace("  - [Agent, HANDLES, Ticket]", "  - [Agent, HANDLES, Ticket]\n  - [Agent, OPENED, Ticket]")
             .replace("  - [Customer, OPENED, Ticket]\n", ""))

    assert summary(d) == [("OPENED", "changed", "additive"), ("OPENED", "changed", "breaking")]
    widened, narrowed = d.changes
    assert "(Agent)-[OPENED]->(Ticket)" in widened.detail
    assert "(Customer)-[OPENED]->(Ticket)" in narrowed.detail


def test_narrowing_a_propertys_type_is_breaking(diff):
    d = diff(BASE.replace("{name: priority, type: FLOAT}", "{name: priority, type: INTEGER}"))

    assert summary(d) == [("Ticket.priority", "changed", "breaking")]
    assert d.changes[0].concept_kind == "property"
    assert "FLOAT -> INTEGER" in d.changes[0].detail


def test_widening_a_propertys_type_is_additive(client):
    d = client.diff_ontologies(
        BASE.replace("{name: priority, type: FLOAT}", "{name: priority, type: INTEGER}"), BASE
    )

    assert summary(d) == [("Ticket.priority", "changed", "additive")]


def test_adding_an_optional_property_is_additive_but_a_required_one_is_breaking(diff):
    d = diff(BASE.replace(
        "      - {name: priority, type: FLOAT}",
        "      - {name: priority, type: FLOAT}\n"
        "      - {name: channel, type: STRING}\n"
        "      - {name: status, type: STRING, required: true}",
    ))

    assert summary(d) == [
        ("Ticket.channel", "added", "additive"),
        ("Ticket.status", "added", "breaking"),
    ]


def test_removing_a_property_is_breaking(diff):
    d = diff(BASE.replace("      - {name: priority, type: FLOAT}\n", ""))

    assert summary(d) == [("Ticket.priority", "removed", "breaking")]


def test_making_a_property_required_is_breaking_and_optional_is_additive(diff):
    d = diff(BASE.replace("{name: name, type: STRING, required: true}", "{name: name, type: STRING}")
             .replace("{name: opened_at, type: DATE}", "{name: opened_at, type: DATE, required: true}"))

    assert summary(d) == [
        ("Customer.name", "changed", "additive"),
        ("Ticket.opened_at", "changed", "breaking"),
    ]


def test_marking_a_concept_deprecated_is_deprecating(diff):
    d = diff(BASE.replace("  - Agent", "  - {label: Agent, deprecated: true}"))

    assert summary(d) == [("Agent", "deprecated", "deprecating")]
    assert d.classification == "deprecating"
    assert not d.is_breaking


def test_a_rename_declared_via_replaced_by_is_deprecating(diff):
    d = diff(BASE.replace("[OPENED, HANDLES]", "[OPENED, {label: HANDLES, replacedBy: RESOLVES}, RESOLVES]")
             + "  - [Agent, RESOLVES, Ticket]\n")

    assert summary(d) == [("HANDLES", "deprecated", "deprecating"), ("RESOLVES", "added", "additive")]
    assert "replaced by RESOLVES" in d.changes[0].detail
    assert d.classification == "deprecating"


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


def test_changing_a_description_is_additive(diff):
    d = diff(BASE.replace("  - label: Ticket\n", "  - label: Ticket\n    description: A support request\n")
             .replace("{name: opened_at, type: DATE}", "{name: opened_at, type: DATE, description: When it was opened}"))

    assert summary(d) == [("Ticket", "changed", "additive"), ("Ticket.opened_at", "changed", "additive")]
