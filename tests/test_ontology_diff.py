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
    assert attributes(d) == [("Ticket", "node_type", "priority")]


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
    # A change to a Concept says what changed, beside the Concept it names: no repeat of it.
    assert d.changes[0].detail == "deprecated; replaced by RESOLVES"
    assert d.classification == "deprecating"
    assert concerns_the_concept_itself(d)


def test_a_diff_groups_its_changes_by_classification(diff):
    d = diff(
        BASE.replace(
            "[OPENED, HANDLES]", "[OPENED, {label: HANDLES, replacedBy: RESOLVES}, RESOLVES]"
        )
        + "  - [Agent, RESOLVES, Ticket]\n"
    )

    assert [c.concept for c in d.deprecating] == ["HANDLES"]
    assert [c.concept for c in d.additive] == ["RESOLVES"]
    assert (d.breaking, d.cosmetic) == ((), ())


def test_undeprecating_is_additive_and_changing_a_replacement_is_deprecating(client):
    deprecated = "node_types: [{label: Agent, deprecated: true}]\n"
    replaced = "node_types: [{label: Agent, replacedBy: Staff}, Staff, Worker]\n"
    retargeted = "node_types: [{label: Agent, replacedBy: Worker}, Staff, Worker]\n"

    undeprecated = client.diff_ontologies(deprecated, "node_types: [Agent]\n")
    changed = client.diff_ontologies(replaced, retargeted)

    assert summary(undeprecated) == [("Agent", "changed", "additive")]
    assert summary(changed) == [("Agent", "deprecated", "deprecating")]
    assert [undeprecated.changes[0].detail, changed.changes[0].detail] == [
        "no longer deprecated",
        "replacement changed Staff -> Worker",
    ]
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


def test_changing_only_definitions_is_cosmetic(diff):
    d = diff(
        BASE.replace("  - Agent", "  - {label: Agent, definition: A support employee}")
        .replace(
            "relationship_types: [OPENED, HANDLES]",
            "relationship_types:\n"
            "  - OPENED\n  - {label: HANDLES, definition: The agent works the ticket}",
        )
        .replace(
            "{name: priority, type: FLOAT}",
            "{name: priority, type: FLOAT, definition: Higher is more urgent}",
        )
    )

    assert [(c.concept, c.classification, c.detail) for c in d.changes] == [
        ("Agent", "cosmetic", "definition changed"),
        ("Ticket.priority", "cosmetic", "definition changed"),
        ("HANDLES", "cosmetic", "definition changed"),
    ]
    assert d.classification == "cosmetic"


def test_changing_only_alternative_labels_is_cosmetic(diff):
    d = diff(
        BASE.replace("  - Agent", "  - {label: Agent, alternativeLabels: [Rep]}").replace(
            "{name: name, type: STRING, required: true}",
            "{name: name, type: STRING, required: true, alternativeLabels: [full_name]}",
        )
    )

    assert [(c.concept, c.classification, c.detail) for c in d.changes] == [
        ("Agent", "cosmetic", "alternative labels changed"),
        ("Customer.name", "cosmetic", "alternative labels changed"),
    ]
    assert d.classification == "cosmetic"


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
    assert attributes(client.diff_ontologies(unique, plain)) == [("Customer", "node_type", "email")]


def _performed_on(cardinality: str | None) -> str:
    pattern = "{source: WorkOrder, relationship: PERFORMED_ON, target: Machine"
    pattern += f", cardinality: {cardinality}}}" if cardinality else "}"
    return (
        "node_types: [WorkOrder, Machine]\nrelationship_types: [PERFORMED_ON]\n"
        f"patterns:\n  - {pattern}\n"
    )


def test_adding_a_cardinality_bound_is_breaking_and_removing_one_is_additive(client):
    unbounded = _performed_on(None)
    exactly_one = _performed_on("{out: {min: 1, max: 1}}")

    added = client.diff_ontologies(unbounded, exactly_one)
    removed = client.diff_ontologies(exactly_one, unbounded)

    assert summary(added) == [
        ("PERFORMED_ON", "changed", "breaking"),
        ("PERFORMED_ON", "changed", "breaking"),
    ]
    assert {c.pattern for c in added.changes} == {Pattern("WorkOrder", "PERFORMED_ON", "Machine")}
    assert summary(removed) == [
        ("PERFORMED_ON", "changed", "additive"),
        ("PERFORMED_ON", "changed", "additive"),
    ]


def test_tightening_a_cardinality_bound_is_breaking_and_loosening_one_is_additive(client):
    loose = _performed_on("{in: {min: 1, max: 5}}")
    tight = _performed_on("{in: {min: 2, max: 3}}")
    shifted = _performed_on("{in: {min: 0, max: 3}}")

    assert summary(client.diff_ontologies(loose, tight)) == [
        ("PERFORMED_ON", "changed", "breaking"),
        ("PERFORMED_ON", "changed", "breaking"),
    ]
    assert summary(client.diff_ontologies(tight, loose)) == [
        ("PERFORMED_ON", "changed", "additive"),
        ("PERFORMED_ON", "changed", "additive"),
    ]
    assert summary(client.diff_ontologies(tight, shifted)) == [
        ("PERFORMED_ON", "changed", "additive")
    ]


def test_a_cardinality_change_between_versions_says_which_bound_changed(client):
    client.create_knowledge_graph(KG, ontology=_performed_on("{out: {max: 2}}"))
    v2 = client.register_ontology(KG, _performed_on("{out: {max: 1}, in: {min: 1}}"))

    d = client.diff_ontology_versions(KG, 1, v2.number)

    assert summary(d) == [
        ("PERFORMED_ON", "changed", "breaking"),
        ("PERFORMED_ON", "changed", "breaking"),
    ]
    assert [c.detail for c in d.changes] == [
        "(WorkOrder)-[PERFORMED_ON]->(Machine) out max 2 -> 1",
        "(WorkOrder)-[PERFORMED_ON]->(Machine) in min (none) -> 1",
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


def test_deprecating_an_attribute_is_deprecating(diff):
    d = diff(
        BASE.replace(
            "{name: opened_at, type: DATE}", "{name: opened_at, type: DATE, deprecated: true}"
        )
    )

    assert summary(d) == [("Ticket.opened_at", "deprecated", "deprecating")]
    assert attributes(d) == [("Ticket", "node_type", "opened_at")]
    assert d.changes[0].detail == "deprecated"
    assert d.classification == "deprecating"


def test_an_attribute_rename_declared_via_replaced_by_is_a_replacement(diff):
    d = diff(
        BASE.replace(
            "{name: priority, type: FLOAT}",
            "{name: priority, type: FLOAT, replacedBy: urgency}\n"
            "      - {name: urgency, type: FLOAT}",
        )
    )

    assert summary(d) == [
        ("Ticket.priority", "deprecated", "deprecating"),
        ("Ticket.urgency", "added", "additive"),
    ]
    assert d.changes[0].detail == "deprecated; replaced by urgency"
    assert d.classification == "deprecating"


def test_changing_only_a_deprecation_reason_is_cosmetic(client):
    def ontology(reason: str) -> str:
        return (
            f"node_types:\n  - {{label: Agent, deprecated: true, deprecationReason: {reason}}}\n"
            "  - label: Ticket\n    properties:\n"
            f"      - {{name: priority, type: FLOAT, deprecated: true, deprecationReason: {reason}}}\n"
            f"relationship_types: [{{label: HANDLES, deprecated: true, deprecationReason: {reason}}}]\n"
        )

    d = client.diff_ontologies(ontology("Unused"), ontology("Nobody reads it"))

    assert [(c.concept, c.classification, c.detail) for c in d.changes] == [
        ("Agent", "cosmetic", "deprecation reason changed"),
        ("Ticket.priority", "cosmetic", "deprecation reason changed"),
        ("HANDLES", "cosmetic", "deprecation reason changed"),
    ]
    assert d.classification == "cosmetic"


def test_deprecating_with_a_reason_is_one_deprecating_change(client):
    d = client.diff_ontologies(
        "node_types: [Agent]\n",
        "node_types: [{label: Agent, deprecated: true, deprecationReason: Unused}]\n",
    )

    assert summary(d) == [("Agent", "deprecated", "deprecating")]


def _with_vocabulary(values: str, binding: str = ", vocabulary: Status", extra: str = "") -> str:
    return (
        f"vocabularies:\n  - {{label: Status, values: [{values}]}}\n{extra}"
        "node_types:\n  - label: WorkOrder\n    properties:\n"
        f"      - {{name: status, type: STRING{binding}}}\n"
    )


def vocabulary_values(d: OntologyDiff) -> list[tuple[str | None, str | None]]:
    """Each change's Vocabulary and Vocabulary Value as the Diff states them."""
    return [(c.vocabulary, c.value) for c in d.changes]


def test_adding_a_vocabulary_value_is_additive(client):
    d = client.diff_ontologies(_with_vocabulary("open"), _with_vocabulary("open, closed"))

    assert summary(d) == [("Status.closed", "added", "additive")]
    assert [c.concept_kind for c in d.changes] == ["vocabulary"]
    assert vocabulary_values(d) == [("Status", "closed")]


def test_deprecating_a_vocabulary_value_is_deprecating(client):
    d = client.diff_ontologies(
        _with_vocabulary("done, closed"),
        _with_vocabulary("{label: done, replacedBy: closed}, closed"),
    )

    assert summary(d) == [("Status.done", "deprecated", "deprecating")]
    assert d.changes[0].detail == "deprecated; replaced by closed"
    assert vocabulary_values(d) == [("Status", "done")]


def test_removing_a_vocabulary_value_is_breaking(client):
    d = client.diff_ontologies(_with_vocabulary("open, closed"), _with_vocabulary("open"))

    assert summary(d) == [("Status.closed", "removed", "breaking")]
    assert vocabulary_values(d) == [("Status", "closed")]


def test_binding_a_vocabulary_to_an_existing_attribute_is_breaking(client):
    d = client.diff_ontologies(_with_vocabulary("open", binding=""), _with_vocabulary("open"))

    assert summary(d) == [("WorkOrder.status", "changed", "breaking")]
    assert attributes(d) == [("WorkOrder", "node_type", "status")]
    assert d.changes[0].detail == "bound to Vocabulary Status"


def test_binding_an_attribute_to_another_vocabulary_is_breaking(client):
    other = "  - {label: Phase, values: [open]}\n"
    d = client.diff_ontologies(
        _with_vocabulary("open", extra=other),
        _with_vocabulary("open", binding=", vocabulary: Phase", extra=other),
    )

    assert summary(d) == [("WorkOrder.status", "changed", "breaking")]
    assert d.changes[0].detail == "Vocabulary Status -> Phase"


def test_unbinding_a_vocabulary_is_additive(client):
    d = client.diff_ontologies(_with_vocabulary("open"), _with_vocabulary("open", binding=""))

    assert summary(d) == [("WorkOrder.status", "changed", "additive")]
    assert d.changes[0].detail == "no longer bound to Vocabulary Status"


def test_adding_or_removing_an_unbound_vocabulary_is_additive(client):
    without = "node_types: [WorkOrder]\n"
    with_ = "vocabularies:\n  - {label: Status, values: [open]}\nnode_types: [WorkOrder]\n"

    added, removed = client.diff_ontologies(without, with_), client.diff_ontologies(with_, without)

    assert summary(added) == [("Status", "added", "additive")]
    assert summary(removed) == [("Status", "removed", "additive")]
    assert [c.concept_kind for c in added.changes + removed.changes] == ["vocabulary"] * 2
    assert vocabulary_values(added) == [("Status", None)]


def test_documentation_changes_on_a_vocabulary_or_its_values_are_cosmetic(client):
    def ontology(definition: str, alternative: str) -> str:
        return (
            f"vocabularies:\n  - label: Status\n    definition: {definition}\n"
            f"    alternativeLabels: [{alternative}]\n    values:\n"
            f"      - {{label: open, definition: {definition}, alternativeLabels: [{alternative}]}}\n"
            "node_types: [WorkOrder]\n"
        )

    d = client.diff_ontologies(ontology("Old", "A"), ontology("New", "B"))

    assert [(c.concept, c.classification, c.detail) for c in d.changes] == [
        ("Status", "cosmetic", "definition changed"),
        ("Status", "cosmetic", "alternative labels changed"),
        ("Status.open", "cosmetic", "definition changed"),
        ("Status.open", "cosmetic", "alternative labels changed"),
    ]
    assert d.classification == "cosmetic"


def test_changing_only_a_vocabulary_values_deprecation_reason_is_cosmetic(client):
    def ontology(reason: str) -> str:
        return _with_vocabulary(f"{{label: done, deprecated: true, deprecationReason: {reason}}}")

    d = client.diff_ontologies(ontology("Old"), ontology("Unused"))

    assert summary(d) == [("Status.done", "changed", "cosmetic")]
