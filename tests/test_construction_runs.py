"""Construction Runs and Observation, through the SDK, against the in-memory fake Graph Source."""

import pytest

import stetiq
from stetiq.graph_source import GraphSourceScope


def test_a_knowledge_graph_can_be_bound_to_a_graph_source_scope(client, support_ontology):
    client.create_knowledge_graph("support", ontology=support_ontology)

    client.bind_graph_source("support", GraphSourceScope(database="neo4j", label="KG_support"))

    assert client.get_graph_source("support") == GraphSourceScope(
        database="neo4j", label="KG_support"
    )


def test_binding_again_replaces_the_scope(client, support_ontology):
    client.create_knowledge_graph("support", ontology=support_ontology)
    client.bind_graph_source("support", GraphSourceScope(database="neo4j", label="KG_old"))

    client.bind_graph_source("support", GraphSourceScope(database="kgs", namespace="support"))

    assert client.get_graph_source("support") == GraphSourceScope(
        database="kgs", namespace="support"
    )


def test_an_unbound_knowledge_graph_has_no_graph_source(client, support_ontology):
    client.create_knowledge_graph("support", ontology=support_ontology)

    with pytest.raises(stetiq.GraphSourceNotBoundError):
        client.get_graph_source("support")


def test_binding_an_unknown_knowledge_graph_fails(client):
    with pytest.raises(stetiq.NotFoundError):
        client.bind_graph_source("nope", GraphSourceScope(database="neo4j"))


SCOPE = GraphSourceScope(database="neo4j", label="KG_support")

EVOLVED_ONTOLOGY = """
node_types: [Customer, Ticket, Agent]
relationship_types: [OPENED]
patterns: [[Customer, OPENED, Ticket]]
"""


@pytest.fixture
def support_kg(client, support_ontology):
    client.create_knowledge_graph("support", ontology=support_ontology)
    client.bind_graph_source("support", SCOPE)
    return "support"


def test_start_run_binds_to_the_given_ontology_version_and_returns_its_declared_ontology(
    client, support_kg
):
    client.register_ontology(support_kg, EVOLVED_ONTOLOGY)

    run = client.start_run(support_kg, ontology_version=2)

    assert run.ontology_version == 2
    assert run.declared_ontology == client.get_ontology_version(support_kg, 2).ontology
    assert run.declared_ontology.node_type("Agent") is not None
    assert client.get_run(run.id).status == "running"
    assert client.get_run(run.id).ontology_version == 2


def test_starting_a_run_on_an_unknown_ontology_version_fails(client, support_kg):
    with pytest.raises(stetiq.NotFoundError):
        client.start_run(support_kg, ontology_version=7)

    assert client.list_runs(support_kg) == []


def test_starting_a_run_needs_a_bound_graph_source(client, support_ontology):
    client.create_knowledge_graph("unbound", ontology=support_ontology)

    with pytest.raises(stetiq.GraphSourceNotBoundError):
        client.start_run("unbound", ontology_version=1)


def test_params_and_metrics_can_be_logged_on_a_run(client, support_kg):
    run = client.start_run(support_kg, ontology_version=1)

    run.log_param("llm", "gpt-x")
    run.log_params({"prompt_version": 3, "threshold": 0.5})
    run.log_metric("chunks", 120)
    run.log_metrics({"extraction_seconds": 4.25, "chunks": 130})

    logged = client.get_run(run.id)
    assert logged.params == {"llm": "gpt-x", "prompt_version": "3", "threshold": "0.5"}
    assert logged.metrics == {"chunks": 130.0, "extraction_seconds": 4.25}


def _seed_support_graph(graph_source):
    ada = graph_source.add_node(["KG_support", "Customer"], {"name": "Ada"})
    bob = graph_source.add_node(["KG_support", "Customer"], {"name": "Bob"})
    t1 = graph_source.add_node(["KG_support", "Ticket"], {"opened_at": "2026-01-01"})
    t2 = graph_source.add_node(["KG_support", "Ticket"])
    graph_source.add_relationship(ada, "OPENED", t1)
    graph_source.add_relationship(ada, "OPENED", t2)
    graph_source.add_node(["Customer"], {"name": "out of scope"})
    return bob


def test_ending_a_run_observes_the_whole_scope_and_stores_the_observed_schema(
    client, support_kg, graph_source
):
    run = client.start_run(support_kg, ontology_version=1)
    _seed_support_graph(graph_source)  # the pipeline writes into the graph database

    ended = run.end()

    assert ended.status == "finished"
    assert ended.ended_at is not None
    observation = client.get_observation(ended.observation_id)
    assert observation.run_id == run.id
    assert observation.scope == SCOPE
    schema = observation.schema
    assert [(n.label, n.count) for n in schema.node_types] == [("Customer", 2), ("Ticket", 2)]
    assert [(p.name, p.fill_rate) for p in schema.node_type("Customer").properties] == [
        ("name", 1.0)
    ]
    assert [(p.name, p.fill_rate) for p in schema.node_type("Ticket").properties] == [
        ("opened_at", 0.5)
    ]
    assert schema.relationship_type("OPENED").count == 2
    opened = schema.pattern("Customer", "OPENED", "Ticket")
    assert (opened.count, opened.out_degree.max, opened.out_degree.mean) == (2, 2, 1.0)
    assert [o.id for o in client.list_observations(support_kg)] == [observation.id]


def test_an_observation_stores_no_individual_entities(client, support_kg, graph_source):
    _seed_support_graph(graph_source)

    ended = client.start_run(support_kg, ontology_version=1).end()

    observation = client.get_observation(ended.observation_id)
    assert "Ada" not in repr(observation)
    assert "2026-01-01" not in repr(observation)


def test_a_run_used_as_context_manager_ends_with_an_observation(client, support_kg, graph_source):
    with client.start_run(support_kg, ontology_version=1) as run:
        _seed_support_graph(graph_source)

    finished = client.get_run(run.id)
    assert finished.status == "finished"
    assert client.get_observation(finished.observation_id).schema.node_type("Customer").count == 2


def test_a_crashed_run_is_recorded_as_failed_without_an_observation(client, support_kg):
    with pytest.raises(RuntimeError), client.start_run(support_kg, ontology_version=1) as run:
        raise RuntimeError("extractor crashed")

    failed = client.get_run(run.id)
    assert failed.status == "failed"
    assert failed.ended_at is not None
    assert failed.observation_id is None
    assert client.list_observations(support_kg) == []


def test_an_aborted_run_is_recorded_as_failed(client, support_kg):
    run = client.start_run(support_kg, ontology_version=1)

    run.fail()

    assert client.get_run(run.id).status == "failed"
    assert client.list_observations(support_kg) == []


def test_a_run_whose_observation_fails_is_recorded_as_failed(client, support_kg, graph_source):
    run = client.start_run(support_kg, ontology_version=1)
    graph_source.add_node(["KG_support", "Customer"], {"blob": object()})  # unobservable value

    with pytest.raises(TypeError):
        run.end()

    assert client.get_run(run.id).status == "failed"


def test_an_ended_run_accepts_no_more_logging_or_ending(client, support_kg):
    run = client.start_run(support_kg, ontology_version=1)
    run.end()

    with pytest.raises(stetiq.RunNotActiveError):
        run.log_metric("late", 1.0)
    with pytest.raises(stetiq.RunNotActiveError):
        run.end()
    assert client.get_run(run.id).status == "finished"


def test_runs_can_be_listed_with_the_ontology_version_each_consumed(client, support_kg):
    client.register_ontology(support_kg, EVOLVED_ONTOLOGY)
    first = client.start_run(support_kg, ontology_version=1)
    first.end()
    second = client.start_run(support_kg, ontology_version=2)
    second.fail()
    third = client.start_run(support_kg, ontology_version=2)

    runs = client.list_runs(support_kg)

    assert [(r.id, r.ontology_version, r.status) for r in runs] == [
        (first.id, 1, "finished"),
        (second.id, 2, "failed"),
        (third.id, 2, "running"),
    ]


def test_runs_can_be_compared_side_by_side(client, support_kg):
    client.register_ontology(support_kg, EVOLVED_ONTOLOGY)
    with client.start_run(support_kg, ontology_version=1) as a:
        a.log_params({"llm": "gpt-x", "prompt_version": 1})
        a.log_metrics({"chunks": 100})
    with client.start_run(support_kg, ontology_version=2) as b:
        b.log_params({"llm": "claude"})
        b.log_metrics({"chunks": 90, "cost_usd": 1.5})

    comparison = client.compare_runs([a.id, b.id])

    assert [r.id for r in comparison.runs] == [a.id, b.id]
    assert comparison.ontology_versions == (1, 2)
    assert comparison.params == {"llm": ("gpt-x", "claude"), "prompt_version": ("1", None)}
    assert comparison.metrics == {"chunks": (100.0, 90.0), "cost_usd": (None, 1.5)}


def test_run_comparison_includes_conformance_and_evaluator_results(client, support_kg):
    class Triples(stetiq.ConstructionRunEvaluator):
        name = "triples"

        def evaluate(self, run):
            return stetiq.Evaluation(metrics={"count": float(run.run.params["chunks"]) * 3})

    client.register_evaluator(Triples())
    with client.start_run(support_kg, ontology_version=1) as a:
        a.log_params({"chunks": 10})
    with client.start_run(support_kg, ontology_version=1) as b:
        b.log_params({"chunks": 20})
    c = client.start_run(support_kg, ontology_version=1)
    c.fail()  # no Observation: no Conformance, no Evaluator results

    comparison = client.compare_runs([a.id, b.id, c.id])

    a_conformance = client.get_run(a.id).conformance
    assert a_conformance is not None
    assert comparison.conformance == (a_conformance, client.get_run(b.id).conformance, None)
    assert comparison.evaluations["triples.count"] == (30.0, 60.0, None)
    assert comparison.evaluations["conformance.score"] == (
        a_conformance.score,
        a_conformance.score,
        None,
    )


def test_runs_persist_across_clients(client_factory, support_ontology):
    first = client_factory()
    first.create_knowledge_graph("support", ontology=support_ontology)
    first.bind_graph_source("support", SCOPE)
    run = first.start_run("support", ontology_version=1)
    run.log_param("llm", "gpt-x")

    second = client_factory()

    assert second.get_run(run.id).params == {"llm": "gpt-x"}
    assert second.get_graph_source("support") == SCOPE


def test_a_client_without_a_graph_source_adapter_cannot_start_runs(tmp_path):
    client = stetiq.Client(f"sqlite:///{tmp_path / 'other.db'}")
    client.create_knowledge_graph("support", ontology="node_types: [Customer]")
    client.bind_graph_source("support", SCOPE)

    with pytest.raises(stetiq.GraphSourceUnavailableError):
        client.start_run("support", ontology_version=1)

    assert client.list_runs("support") == []
