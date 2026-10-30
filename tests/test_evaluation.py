"""Evaluator framework and the built-in reference-free structural Evaluators."""

import pytest

import stetiq
from stetiq.evaluation import Detail, Evaluation, OntologyVersionEvaluator

# Agent is in no pattern (isolated); ESCALATES is used by no pattern (orphan).
WITH_ISOLATED_AGENT = """
node_types:
  - label: Customer
    properties:
      - {name: name, type: STRING, required: true}
  - Ticket
  - Agent
relationship_types: [OPENED, ESCALATES]
patterns:
  - [Customer, OPENED, Ticket]
"""


@pytest.fixture
def kg(client, support_ontology):
    return client.create_knowledge_graph("customer-support-kg", ontology=support_ontology)


def by_evaluator(results):
    return {r.evaluator: r for r in results}


def test_built_in_evaluators_run_automatically_on_a_new_ontology_version(client, kg):
    version = client.register_ontology(kg.name, WITH_ISOLATED_AGENT)

    results = by_evaluator(client.get_evaluation_results(kg.name, version.number))

    isolated = results["isolated_node_types"]
    assert isolated.metrics == {"isolated_node_types": 1, "isolated_node_type_ratio": 1 / 3}
    assert [(d.item, d.metric) for d in isolated.details] == [("Agent", "isolated_node_types")]
    assert isolated.subject_kind == "ontology_version"
    assert (isolated.knowledge_graph, isolated.subject_id) == (kg.name, "2")


class UndescribedConcepts(OntologyVersionEvaluator):
    """A domain rule: every node type needs a description."""

    name = "undescribed_concepts"

    def evaluate(self, version):
        missing = [n.label for n in version.ontology.node_types if not n.description]
        return Evaluation(
            metrics={"undescribed": len(missing)},
            details=[Detail(label, "has no description") for label in missing],
        )


def test_a_custom_evaluator_runs_on_new_versions_alongside_the_built_ins(client, kg):
    client.register_evaluator(UndescribedConcepts())

    version = client.register_ontology(kg.name, WITH_ISOLATED_AGENT)

    results = by_evaluator(client.get_evaluation_results(kg.name, version.number))
    assert {"isolated_node_types", "undescribed_concepts"} <= set(results)
    custom = results["undescribed_concepts"]
    assert custom.metrics == {"undescribed": 3}
    assert sorted(d.item for d in custom.details) == ["Agent", "Customer", "Ticket"]


def test_custom_results_are_visible_to_other_clients(client_factory, kg):
    writer = client_factory()
    writer.register_evaluator(UndescribedConcepts())
    version = writer.register_ontology(kg.name, WITH_ISOLATED_AGENT)

    results = by_evaluator(client_factory().get_evaluation_results(kg.name, version.number))

    assert results["undescribed_concepts"].metrics == {"undescribed": 3}


def test_evaluation_can_be_re_run_on_demand_for_an_existing_version(client, kg):
    before = by_evaluator(client.get_evaluation_results(kg.name, 1))
    assert "undescribed_concepts" not in before
    client.register_evaluator(UndescribedConcepts())

    rerun = by_evaluator(client.evaluate(kg.name, 1))

    assert rerun["undescribed_concepts"].metrics == {"undescribed": 1}  # Customer
    assert rerun["isolated_node_types"].created_at > before["isolated_node_types"].created_at
    assert by_evaluator(client.get_evaluation_results(kg.name, 1)) == rerun


class Returns(OntologyVersionEvaluator):
    def __init__(self, name, metrics):
        self.name, self._metrics = name, metrics

    def evaluate(self, version):
        return Evaluation(metrics=self._metrics)


class Crashes(OntologyVersionEvaluator):
    name = "crashes"

    def evaluate(self, version):
        raise RuntimeError("boom")


def test_a_custom_evaluator_cannot_shadow_a_built_in_or_another_registration(client):
    client.register_evaluator(UndescribedConcepts())

    with pytest.raises(stetiq.EvaluatorError, match="isolated_node_types"):
        client.register_evaluator(Returns("isolated_node_types", {}))
    with pytest.raises(stetiq.EvaluatorError, match="undescribed_concepts"):
        client.register_evaluator(UndescribedConcepts())
    with pytest.raises(stetiq.EvaluatorError):
        client.register_evaluator(lambda version: {})


def test_an_invalid_metric_is_rejected_naming_the_evaluator(client, kg):
    client.register_evaluator(Returns("bad_metric", {"score": "high"}))

    with pytest.raises(stetiq.EvaluatorError, match=r"bad_metric.*score"):
        client.evaluate(kg.name, 1)

    assert "bad_metric" not in by_evaluator(client.get_evaluation_results(kg.name, 1))


def test_a_failing_custom_evaluator_reports_its_name_and_the_version_still_exists(client, kg):
    client.register_evaluator(Crashes())

    with pytest.raises(stetiq.EvaluatorError, match=r"crashes.*boom"):
        client.register_ontology(kg.name, WITH_ISOLATED_AGENT)

    assert [v.number for v in client.list_ontology_versions(kg.name)] == [1, 2]
    assert "isolated_node_types" in by_evaluator(client.get_evaluation_results(kg.name, 2))


HIERARCHY = """
node_types:
  - Party
  - {label: Customer, parent: Party}
  - {label: Agent, parent: Party}
  - {label: Supervisor, parent: Agent}
  - Ticket
relationship_types: [OPENED, HANDLES]
patterns:
  - [Customer, OPENED, Ticket]
  - [Agent, HANDLES, Ticket]
"""


def test_hierarchy_depth_and_breadth_are_measured(client):
    client.create_knowledge_graph("kg", ontology=HIERARCHY)

    hierarchy = by_evaluator(client.get_evaluation_results("kg", 1))["hierarchy"]

    # Levels: {Party, Ticket}, {Customer, Agent}, {Supervisor}.
    assert hierarchy.metrics == {
        "max_depth": 3,
        "max_breadth": 2,
        "root_node_types": 2,
        "max_children": 2,
    }


def test_a_flat_ontology_has_depth_one(client, kg):
    hierarchy = by_evaluator(client.get_evaluation_results(kg.name, 1))["hierarchy"]

    assert hierarchy.metrics == {
        "max_depth": 1,
        "max_breadth": 2,
        "root_node_types": 2,
        "max_children": 0,
    }


def test_node_types_connected_through_the_hierarchy_are_not_isolated(client):
    # Supervisor inherits Agent's HANDLES; Party is the supertype of pattern participants.
    with_location = HIERARCHY.replace("  - Ticket\n", "  - Ticket\n  - Location\n")
    client.create_knowledge_graph("kg", ontology=with_location)

    isolated = by_evaluator(client.get_evaluation_results("kg", 1))["isolated_node_types"]

    assert [d.item for d in isolated.details] == ["Location"]
    assert isolated.metrics["isolated_node_types"] == 1


def test_orphan_concepts_are_those_nothing_else_refers_to(client, kg):
    version = client.register_ontology(kg.name, WITH_ISOLATED_AGENT)

    orphans = by_evaluator(client.get_evaluation_results(kg.name, version.number))[
        "orphan_concepts"
    ]

    # ESCALATES is in no pattern; Agent is in no pattern and outside any hierarchy.
    assert orphans.metrics == {
        "orphan_concepts": 2,
        "orphan_node_types": 1,
        "orphan_relationship_types": 1,
        "orphan_concept_ratio": 2 / 5,
    }
    assert sorted((d.item, d.metric) for d in orphans.details) == [
        ("Agent", "orphan_node_types"),
        ("ESCALATES", "orphan_relationship_types"),
    ]


REDUNDANT = """
node_types:
  - label: Party
    properties: [{name: name, type: STRING}]
  - label: Customer
    parent: Party
    properties: [{name: name, type: STRING}]   # restates Party.name
  - label: Ticket
    properties: [{name: title, type: STRING}, {name: opened_at, type: DATE}]
  - label: Case
    properties: [{name: opened_at, type: DATE}, {name: title, type: STRING}]
relationship_types: [OPENED]
patterns:
  - [Party, OPENED, Ticket]
  - [Customer, OPENED, Ticket]   # implied by the pattern above
  - [Party, OPENED, Case]
"""


def test_redundancy_finds_implied_patterns_restated_properties_and_duplicate_structure(client):
    client.create_knowledge_graph("kg", ontology=REDUNDANT)

    redundancy = by_evaluator(client.get_evaluation_results("kg", 1))["redundancy"]

    assert redundancy.metrics == {
        "redundant_patterns": 1,
        "redundant_properties": 1,
        "duplicate_structure_concepts": 2,
    }
    assert sorted((d.metric, d.item) for d in redundancy.details) == [
        ("duplicate_structure_concepts", "Case"),
        ("duplicate_structure_concepts", "Ticket"),
        ("redundant_patterns", "(Customer)-[OPENED]->(Ticket)"),
        ("redundant_properties", "Customer.name"),
    ]


CONSTRAINED = """
node_types:
  - label: Party
    properties: [{name: email, type: STRING, required: true}]
  - label: Customer
    parent: Party
    properties: [{name: number, type: STRING}]
  - {label: Lead, deprecated: true, replacedBy: Prospect, properties: [{name: email, type: STRING}]}
  - {label: Prospect, deprecated: true}
relationship_types: [REFERS]
patterns:
  - [Customer, REFERS, Lead]
constraints:
  - {type: UNIQUENESS, node_type: Party, property_name: email}
  - {type: UNIQUENESS, node_type: Customer, property_name: email}    # already unique via Party
  - {type: UNIQUENESS, node_type: Customer, property_name: number}   # unique but optional
  - {type: UNIQUENESS, node_type: Lead, property_name: email}        # on a deprecated node type
"""


def test_constraint_consistency_flags_contradictory_or_redundant_constraints(client):
    client.create_knowledge_graph("kg", ontology=CONSTRAINED)

    consistency = by_evaluator(client.get_evaluation_results("kg", 1))["constraint_consistency"]

    assert consistency.metrics == {
        "inconsistencies": 5,
        "inherited_duplicate_constraints": 1,
        "unique_optional_properties": 2,
        "constraints_on_deprecated": 1,
        "deprecated_replacements": 1,
    }
    assert sorted((d.metric, d.item) for d in consistency.details) == [
        ("constraints_on_deprecated", "Lead.email"),
        ("deprecated_replacements", "Lead"),
        ("inherited_duplicate_constraints", "Customer.email"),
        ("unique_optional_properties", "Customer.number"),
        ("unique_optional_properties", "Lead.email"),
    ]


def test_a_consistent_ontology_has_no_inconsistencies(client, kg):
    consistency = by_evaluator(client.get_evaluation_results(kg.name, 1))["constraint_consistency"]

    assert consistency.metrics["inconsistencies"] == 0
    assert consistency.details == ()


class RunLevel(stetiq.ConstructionRunEvaluator):
    name = "run_level"

    def evaluate(self, run):
        raise AssertionError("run-level Evaluators never see an Ontology Version")


def test_a_run_level_evaluator_is_accepted_but_not_applied_to_ontology_versions(client, kg):
    client.register_evaluator(RunLevel())

    client.register_ontology(kg.name, WITH_ISOLATED_AGENT)

    assert "run_level" not in by_evaluator(client.evaluate(kg.name, 2))


def test_re_running_evaluation_on_a_missing_version_is_not_found(client, kg):
    with pytest.raises(stetiq.NotFoundError):
        client.evaluate(kg.name, 7)
    with pytest.raises(stetiq.NotFoundError):
        client.get_evaluation_results(kg.name, 7)


# --- Every version's results at once (the web UI's version list) -------------------------


def test_the_latest_results_of_every_ontology_version_are_listed_in_one_call(client, kg):
    client.register_ontology(kg.name, WITH_ISOLATED_AGENT)
    client.register_evaluator(UndescribedConcepts())
    client.evaluate(kg.name, 1)  # a newer result for each of v1's Evaluators

    results = client.list_evaluation_results(kg.name)

    keys = [(r.subject_id, r.evaluator) for r in results]
    assert len(keys) == len(set(keys))  # only the latest per (version, Evaluator)
    assert {r.subject_kind for r in results} == {"ontology_version"}
    assert by_evaluator(r for r in results if r.subject_id == "1") == by_evaluator(
        client.get_evaluation_results(kg.name, 1)
    )
    assert by_evaluator(r for r in results if r.subject_id == "2") == by_evaluator(
        client.get_evaluation_results(kg.name, 2)
    )
    assert "undescribed_concepts" not in by_evaluator(r for r in results if r.subject_id == "2")


def test_results_are_listed_per_subject_kind(client, kg):
    assert client.list_evaluation_results(kg.name, "construction_run") == []


def test_listing_results_needs_a_known_knowledge_graph_and_subject_kind(client, kg):
    with pytest.raises(stetiq.NotFoundError):
        client.list_evaluation_results("nope")
    with pytest.raises(stetiq.EvaluatorError, match="subject kind"):
        client.list_evaluation_results(kg.name, "observation")
