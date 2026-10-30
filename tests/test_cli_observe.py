"""CLI smoke tests for `stetiq observe` exit codes and `stetiq drift list`.

The Graph Source adapter is normally built from $STETIQ_GRAPH_SOURCE_URI; here the
env-builder is pointed at the in-memory fake instead."""

from datetime import date

import pytest
from typer.testing import CliRunner

import stetiq
from stetiq.cli import DRIFT_EXIT_CODE, app
from stetiq.graph_source import GraphSourceScope, InMemoryGraphSource


@pytest.fixture
def cli_env(tmp_path, monkeypatch, support_ontology):
    uri = f"sqlite:///{tmp_path / 'stetiq.db'}"
    monkeypatch.setenv("STETIQ_TRACKING_URI", uri)
    monkeypatch.chdir(tmp_path)  # the default config path is ./stetiq.yaml
    graph = InMemoryGraphSource()
    monkeypatch.setattr("stetiq.client.graph_source_from_env", lambda environ=None: graph)
    client = stetiq.Client(uri, graph_source=graph)
    client.create_knowledge_graph("support", ontology=support_ontology)
    client.bind_graph_source("support", GraphSourceScope(database="neo4j"))
    ada = graph.add_node(["Customer"], {"name": "Ada"})
    for _ in range(10):
        graph.add_relationship(
            ada, "OPENED", graph.add_node(["Ticket"], {"opened_at": date(2026, 1, 1)})
        )
    return graph, client


def test_observe_exits_zero_without_drift(cli_env):
    result = CliRunner().invoke(app, ["observe", "support"])

    assert result.exit_code == 0, result.output
    assert "No Drift" in result.output


def test_observe_exits_non_zero_on_structural_drift_and_lists_the_event(cli_env):
    graph, _ = cli_env
    graph.add_node(["Agent"], {"name": "Grace"})
    runner = CliRunner()

    observed = runner.invoke(app, ["observe", "support"])
    listed = runner.invoke(app, ["drift", "list", "support"])

    assert observed.exit_code == DRIFT_EXIT_CODE != 0
    assert "undeclared" in observed.output and "Agent" in observed.output
    assert listed.exit_code == 0, listed.output
    assert len(listed.output.strip().splitlines()) == 2  # header + one event


def test_observe_reads_statistical_thresholds_and_the_kg_from_the_repo_config(cli_env, tmp_path):
    graph, client = cli_env
    (tmp_path / "stetiq.yaml").write_text(
        "knowledge_graph: support\ngates: []\ndrift:\n  max_count_increase: 0.1\n"
    )
    runner = CliRunner()
    first = runner.invoke(app, ["observe"])
    ada = graph.add_node(["Customer"], {"name": "Bob"}, database="later")
    for _ in range(12):
        graph.add_relationship(
            ada,
            "OPENED",
            graph.add_node(["Ticket"], {"opened_at": date(2026, 1, 2)}, database="later"),
        )
    client.bind_graph_source("support", GraphSourceScope(database="later"))

    second = runner.invoke(app, ["observe"])

    assert first.exit_code == 0, first.output
    assert second.exit_code == DRIFT_EXIT_CODE, second.output
    assert "count_increase" in second.output and "Ticket" in second.output


def test_observe_exits_one_on_a_malformed_config(cli_env, tmp_path):
    config = tmp_path / "custom.yaml"
    config.write_text("drift:\n  max_count_drop: lots\n")

    result = CliRunner().invoke(app, ["observe", "support", "--config", str(config)])

    assert result.exit_code == 1
    assert "max_count_drop" in result.output
