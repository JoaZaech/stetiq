"""Checking observed values against Vocabularies: Conformance, Drift and Evolution Mode,
through the SDK, against the in-memory fake Graph Source."""

import pytest
from typer.testing import CliRunner

import stetiq
from stetiq.cli import DRIFT_EXIT_CODE, app
from stetiq.graph_source import GraphSourceScope, InMemoryGraphSource

WORK_ORDERS = """
vocabularies:
  - label: Status
    values:
      - open
      - closed
      - {label: done, deprecated: true, replacedBy: closed}
node_types:
  - label: WorkOrder
    properties:
      - {name: status, type: STRING, vocabulary: Status}
"""


@pytest.fixture
def plant(client):
    client.create_knowledge_graph("plant", ontology=WORK_ORDERS)
    client.bind_graph_source("plant", GraphSourceScope(database="neo4j"))
    return "plant"


def seed(graph_source, *statuses):
    for status in statuses:
        graph_source.add_node(["WorkOrder"], {"status": status})


def run_once(client, kg):
    with client.start_run(kg) as run:
        pass
    return client.get_run(run.id)


def value_mismatches(conformance):
    return [
        (m.subject, m.kind, m.value, m.count)
        for m in conformance.mismatches
        if m.kind in ("value_outside_vocabulary", "deprecated_value")
    ]


# --- Conformance --------------------------------------------------------------------


def test_values_inside_the_vocabulary_conform(client, plant, graph_source):
    seed(graph_source, "open", "closed", "open")

    run = run_once(client, plant)

    assert run.conformance.mismatches == ()
    assert run.conformance.score == 1.0


def test_an_out_of_vocabulary_value_is_a_mismatch_with_its_count_and_lowers_the_score(
    client, plant, graph_source
):
    seed(graph_source, "open", "on_hold", "on_hold", "blocked")

    run = run_once(client, plant)

    assert value_mismatches(run.conformance) == [
        ("WorkOrder.status", "value_outside_vocabulary", "on_hold", 2),
        ("WorkOrder.status", "value_outside_vocabulary", "blocked", 1),
    ]
    # Items: WorkOrder, WorkOrder.status, and the status Vocabulary check, which fails.
    assert run.conformance.score == 2 / 3


def test_an_observed_deprecated_value_is_reported_but_conforms(client, plant, graph_source):
    seed(graph_source, "open", "done", "done")

    run = run_once(client, plant)

    assert [(m.kind, m.value, m.count, m.detail) for m in run.conformance.mismatches] == [
        (
            "deprecated_value",
            "done",
            2,
            "'done' observed 2 times, deprecated in Status, replaced by 'closed'",
        ),
    ]
    assert run.conformance.score == 1.0


def test_an_attribute_without_observed_values_is_not_checked(client, plant, graph_source):
    graph_source.add_node(["WorkOrder"], {})  # status never set: absent from the schema

    run = run_once(client, plant)

    assert [(m.subject, m.kind) for m in run.conformance.mismatches] == [
        ("WorkOrder.status", "absent")
    ]
    assert run.conformance.score == 1 / 2


def test_a_truncated_value_list_conforms_when_every_listed_value_is_in_the_vocabulary(
    client_factory, graph_source
):
    client = client_factory(value_cap=2)
    client.create_knowledge_graph("plant", ontology=WORK_ORDERS)
    client.bind_graph_source("plant", GraphSourceScope(database="neo4j"))
    seed(graph_source, "open", "open", "closed", "closed", "on_hold")

    run = run_once(client, "plant")

    assert run.conformance.mismatches == ()
    assert run.conformance.score == 1.0


# --- Drift --------------------------------------------------------------------------


def test_an_out_of_vocabulary_value_is_structural_drift(client, plant, graph_source):
    seed(graph_source, "open", "on_hold", "on_hold", "done")

    outcome = client.observe(plant)

    assert [
        (f.kind, f.subject, f.subject_kind, f.value, f.detail) for f in outcome.drift.findings
    ] == [
        (
            "undeclared_value",
            "WorkOrder.status",
            "property",
            "on_hold",
            "'on_hold' observed 2 times, not a value of Status",
        ),
    ]
    assert outcome.drift.structural == outcome.drift.findings
    assert client.list_drift_events(plant)[0].findings == outcome.drift.findings


def test_values_inside_the_contracts_vocabulary_raise_no_drift(client, plant, graph_source):
    seed(graph_source, "open", "closed", "done")

    assert client.observe(plant).drift is None


def test_stetiq_observe_exits_with_the_drift_code_on_a_new_out_of_vocabulary_value(
    tmp_path, monkeypatch
):
    uri = f"sqlite:///{tmp_path / 'stetiq.db'}"
    monkeypatch.setenv("STETIQ_TRACKING_URI", uri)
    monkeypatch.chdir(tmp_path)
    graph = InMemoryGraphSource()
    monkeypatch.setattr("stetiq.client.graph_source_from_env", lambda environ=None: graph)
    client = stetiq.Client(uri, graph_source=graph)
    client.create_knowledge_graph("plant", ontology=WORK_ORDERS)
    client.bind_graph_source("plant", GraphSourceScope(database="neo4j"))
    seed(graph, "open", "closed")
    assert CliRunner().invoke(app, ["observe", "plant"]).exit_code == 0

    seed(graph, "on_hold")
    result = CliRunner().invoke(app, ["observe", "plant"])

    assert result.exit_code == DRIFT_EXIT_CODE, result.output
    assert "undeclared_value" in result.output
    assert "'on_hold' observed 1 time, not a value of Status" in result.output


# --- Evolution Mode -----------------------------------------------------------------

EVOLVED = """
vocabularies:
  - label: Status
    values:
      - open
      - closed
      - {label: done, deprecated: true, replacedBy: closed}
      - blocked
      - on_hold
node_types:
  - label: WorkOrder
    properties:
      - {name: status, type: STRING, vocabulary: Status}
"""


def test_an_evolving_run_yields_a_candidate_whose_vocabulary_includes_the_new_values(
    client, plant, graph_source
):
    seed(graph_source, "open", "on_hold", "blocked", "done")

    run = run_once(client, plant)

    assert run.status == "finished"
    assert run.candidate_version == 2
    candidate = client.get_ontology_version(plant, 2).ontology
    assert client.diff_ontologies(EVOLVED, candidate).changes == ()
    assert [str(c.classification) for c in client.diff_ontology_versions(plant, 1, 2).changes] == [
        "additive",
        "additive",
    ]


def test_a_strict_run_with_an_out_of_vocabulary_value_fails(client, plant, graph_source):
    client.set_evolution_mode(plant, "strict")
    seed(graph_source, "open", "on_hold")

    run = run_once(client, plant)

    assert run.status == "failed"
    assert run.candidate_version is None


def test_a_deprecated_value_proposes_no_candidate(client, plant, graph_source):
    client.set_evolution_mode(plant, "strict")
    seed(graph_source, "open", "done")

    run = run_once(client, plant)

    assert run.status == "finished"
    assert run.candidate_version is None
