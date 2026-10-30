"""Construction Entry Point: stetiq invokes the user's command as a Construction Run."""

import json
import sys

import pytest
import yaml

import stetiq
from stetiq.graph_source import GraphSourceScope

SCOPE = GraphSourceScope(database="neo4j", label="KG_support")

# Plays the user's pipeline: records what stetiq handed it, then exits with the given code.
PIPELINE = """
import json, pathlib, sys
ontology, graph_source, out, code = sys.argv[1:5]
pathlib.Path(out).write_text(json.dumps({
    "ontology": pathlib.Path(ontology).read_text(),
    "graph_source": graph_source,
    "args": sys.argv[5:],
}))
sys.exit(int(code))
"""


@pytest.fixture
def support_kg(client, support_ontology):
    client.create_knowledge_graph("support", ontology=support_ontology)
    client.bind_graph_source("support", SCOPE)
    return "support"


@pytest.fixture
def pipeline(tmp_path):
    script = tmp_path / "pipeline.py"
    script.write_text(PIPELINE)
    record = tmp_path / "record.json"

    def entry_point(exit_code=0, *extra):
        return stetiq.EntryPoint(
            command=(sys.executable, str(script), "{ontology}", "{graph_source}", str(record), str(exit_code), *extra)
        )

    entry_point.record = lambda: json.loads(record.read_text())
    return entry_point


def seed_declared_graph(graph_source):
    customer = graph_source.add_node(["KG_support", "Customer"], {"name": "Ada"})
    ticket = graph_source.add_node(["KG_support", "Ticket"], {})
    graph_source.add_relationship(customer, "OPENED", ticket)


def test_run_entry_point_passes_the_contract_ontology_and_graph_source_then_observes(
    client, support_kg, pipeline, graph_source
):
    seed_declared_graph(graph_source)

    run = client.run_entry_point(support_kg, pipeline())

    assert run.status == "finished"
    assert run.ontology_version == 1
    assert run.observation_id is not None
    assert client.get_observation(run.observation_id).schema.node_type("Customer").count == 1
    record = pipeline.record()
    assert yaml.safe_load(record["ontology"]) == yaml.safe_load(
        client.get_ontology_yaml(support_kg, 1)
    )
    assert json.loads(record["graph_source"]) == {"database": "neo4j", "label": "KG_support", "namespace": None}


def seed_undeclared_concept(graph_source):
    seed_declared_graph(graph_source)
    graph_source.add_node(["KG_support", "Agent"], {})


def test_a_non_zero_exit_fails_the_run_without_observing_or_creating_a_candidate(
    client, support_kg, pipeline, graph_source
):
    seed_undeclared_concept(graph_source)  # would yield a Candidate in evolving mode

    run = client.run_entry_point(support_kg, pipeline(exit_code=3))

    assert run.status == "failed"
    assert run.candidate_version is None
    assert run.observation_id is None
    assert run.params == {"entry_point.exit_code": "3"}
    assert [v.number for v in client.list_ontology_versions(support_kg)] == [1]


def test_a_zero_exit_in_evolving_mode_yields_a_candidate_like_sdk_instrumentation(
    client, support_kg, pipeline, graph_source
):
    seed_undeclared_concept(graph_source)

    run = client.run_entry_point(support_kg, pipeline())

    assert run.status == "finished"
    assert run.candidate_version == 2
    assert run.params == {"entry_point.exit_code": "0"}


def test_a_zero_exit_still_fails_the_run_in_strict_mode_when_new_concepts_appear(
    client, support_kg, pipeline, graph_source
):
    client.set_evolution_mode(support_kg, "strict")
    seed_undeclared_concept(graph_source)

    run = client.run_entry_point(support_kg, pipeline())

    assert run.status == "failed"
    assert run.candidate_version is None


EVOLVED_ONTOLOGY = """
node_types: [Customer, Ticket, Agent]
relationship_types: [OPENED]
patterns: [[Customer, OPENED, Ticket]]
"""


def test_the_declared_ontology_follows_the_contract_alias_unless_overridden(
    client, support_kg, pipeline
):
    client.register_ontology(support_kg, EVOLVED_ONTOLOGY)
    client.set_alias(support_kg, "staging", 2)

    by_contract = client.run_entry_point(support_kg, pipeline())
    by_version = client.run_entry_point(support_kg, pipeline(), ontology_version=2)
    passed_by_version = pipeline.record()["ontology"]
    by_alias = client.run_entry_point(support_kg, pipeline(), alias="staging")

    assert [by_contract.ontology_version, by_version.ontology_version, by_alias.ontology_version] == [1, 2, 2]
    assert [n["label"] for n in yaml.safe_load(passed_by_version)["node_types"]] == ["Agent", "Customer", "Ticket"]


def test_every_placeholder_is_filled_inside_arguments(client, support_kg, pipeline):
    run = client.run_entry_point(
        support_kg,
        pipeline(0, "kg={knowledge_graph}", "v{ontology_version}", "{run_id}", "{database}/{label}/{namespace}", "{other}"),
    )

    assert pipeline.record()["args"] == ["kg=support", "v1", run.id, "neo4j/KG_support/", "{other}"]


def test_a_command_that_cannot_be_started_fails_the_run_and_raises(client, support_kg, tmp_path):
    missing = stetiq.EntryPoint(command=(str(tmp_path / "missing"),))

    with pytest.raises(stetiq.EntryPointError):
        client.run_entry_point(support_kg, missing)

    assert [r.status for r in client.list_runs(support_kg)] == ["failed"]


def test_an_entry_point_is_read_from_the_repo_config_as_a_string_or_a_list():
    assert stetiq.EntryPoint.from_config(
        {"entry_point": {"command": "python build.py --ontology '{ontology}' --scope {graph_source}"}}
    ) == stetiq.EntryPoint(command=("python", "build.py", "--ontology", "{ontology}", "--scope", "{graph_source}"))
    assert stetiq.EntryPoint.from_config(
        {"gates": {}, "entry_point": {"command": ["make", "graph"]}}
    ) == stetiq.EntryPoint(command=("make", "graph"))


@pytest.mark.parametrize(
    "config",
    [{}, {"entry_point": None}, {"entry_point": {}}, {"entry_point": {"command": ""}}, {"entry_point": {"command": [1]}}],
)
def test_a_missing_or_malformed_entry_point_is_rejected(config):
    with pytest.raises(stetiq.InvalidEntryPointError):
        stetiq.EntryPoint.from_config(config)
