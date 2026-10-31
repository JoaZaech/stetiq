"""Gate Previews (ADR 0007): every Construction Run judged, on demand, against the Gate
definitions of the Knowledge Graph's most recent Gate result, without recording anything."""

from datetime import date

import pytest

from stetiq.graph_source import GraphSourceScope

CONFORMANCE = """
gates:
  - name: conformance
    check: conformance
    min_score: 0.95
"""


@pytest.fixture
def bound_kg(client, support_ontology):
    client.create_knowledge_graph("support", ontology=support_ontology)
    client.bind_graph_source("support", GraphSourceScope(database="neo4j"))
    return "support"


def seed_conforming_graph(graph_source):
    customer = graph_source.add_node(["Customer"], {"name": "Ada"})
    ticket = graph_source.add_node(["Ticket"], {"opened_at": date(2026, 1, 1)})
    graph_source.add_relationship(customer, "OPENED", ticket)


def run_once(client, kg):
    with client.start_run(kg) as run:
        pass
    return client.get_run(run.id)


def test_a_knowledge_graph_that_was_never_gated_has_no_previews(client, bound_kg, graph_source):
    seed_conforming_graph(graph_source)
    run_once(client, bound_kg)

    assert client.preview_gates(bound_kg) == []


def test_every_run_is_previewed_against_the_gates_of_the_latest_run_gate_result(
    client, bound_kg, graph_source
):
    graph_source.add_node(["Customer"], {"name": "Grace"})  # no Ticket, no OPENED
    below = run_once(client, bound_kg)
    seed_conforming_graph(graph_source)
    conforming = run_once(client, bound_kg)
    recorded = client.evaluate_gates(bound_kg, CONFORMANCE, run=conforming.id)

    previews = client.preview_gates(bound_kg)

    assert [(p.subject_kind, p.subject_id, p.ontology_version) for p in previews] == [
        ("construction_run", below.id, 1),
        ("construction_run", conforming.id, 1),
    ]
    assert [p.passed for p in previews] == [False, True]
    [outcome] = previews[0].outcomes
    assert outcome.gate.to_dict() == {
        "name": "conformance",
        "check": "conformance",
        "min_score": 0.95,
    }
    assert "< 0.95" in outcome.reasons[0]
    assert {(p.source.subject_kind, p.source.subject_id) for p in previews} == {
        ("construction_run", conforming.id)
    }
    assert previews[0].source.evaluated_at == recorded.evaluated_at


NO_BREAKING = """
gates:
  - name: no-breaking-changes
    check: ontology_diff
    max_classification: deprecating
"""


def test_a_newer_version_gate_result_does_not_replace_the_run_gate_results_definitions(
    client, bound_kg, graph_source
):
    seed_conforming_graph(graph_source)
    run = run_once(client, bound_kg)
    client.evaluate_gates(bound_kg, CONFORMANCE, run=run.id)
    client.evaluate_gates(bound_kg, NO_BREAKING, version=1)

    [preview] = client.preview_gates(bound_kg)

    assert [g.name for g in preview.gates] == ["conformance"]
    assert (preview.source.subject_kind, preview.source.subject_id) == ("construction_run", run.id)


def test_without_a_run_gate_result_the_latest_gate_result_of_any_subject_is_used(
    client, bound_kg, graph_source
):
    seed_conforming_graph(graph_source)
    run_once(client, bound_kg)
    client.evaluate_gates(bound_kg, CONFORMANCE, version=1)
    client.evaluate_gates(bound_kg, NO_BREAKING, version=1)

    [preview] = client.preview_gates(bound_kg)

    assert [g.name for g in preview.gates] == ["no-breaking-changes"]
    assert preview.passed
    assert (preview.source.subject_kind, preview.source.subject_id) == ("ontology_version", "1")


def test_previewing_records_nothing(client, bound_kg, graph_source):
    graph_source.add_node(["Customer"], {"name": "Grace"})  # no Ticket, no OPENED
    run_once(client, bound_kg)
    seed_conforming_graph(graph_source)
    run_once(client, bound_kg)
    # Version 1 stands on the latest (conforming) run, so its recorded result passes.
    assert client.evaluate_gates(bound_kg, CONFORMANCE, version=1).passed
    before = client.list_gate_results(bound_kg)

    failing, _ = client.preview_gates(bound_kg)
    assert not failing.passed and failing.ontology_version == 1
    client.preview_gates(bound_kg)
    client.set_alias(bound_kg, "staging", 1)

    assert client.list_gate_results(bound_kg) == before
    assert client.list_promotions(bound_kg)[-1].gate_result == "passed"
