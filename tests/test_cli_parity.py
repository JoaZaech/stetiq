"""CLI smoke tests for the SDK capabilities CI uses without Python glue: Knowledge
Graph listing, Graph Source binding, Evolution Mode, runs and their evaluations,
Observations, Gate results and Competency Questions."""

import pytest
import yaml
from typer.testing import CliRunner

import stetiq
from stetiq.cli import app
from stetiq.graph_source import GraphSourceScope, InMemoryGraphSource


@pytest.fixture
def cli_env(tmp_path, monkeypatch, support_ontology):
    uri = f"sqlite:///{tmp_path / 'stetiq.db'}"
    monkeypatch.setenv("STETIQ_TRACKING_URI", uri)
    graph = InMemoryGraphSource()
    graph.add_node(["Customer"], {"name": "Ada"})
    monkeypatch.setattr("stetiq.client.graph_source_from_env", lambda environ=None: graph)
    sdk = stetiq.Client(uri, graph_source=graph)
    sdk.create_knowledge_graph("support", ontology=support_ontology)
    return sdk


def _invoke(*args):
    result = CliRunner().invoke(app, list(args))
    assert result.exit_code == 0, result.output
    return result.output


def test_cli_lists_knowledge_graphs(cli_env, support_ontology):
    cli_env.create_knowledge_graph("billing", ontology=support_ontology)

    output = _invoke("kg", "list")

    assert [line.split()[0] for line in output.strip().splitlines()[1:]] == ["billing", "support"]


def test_cli_binds_and_shows_the_graph_source(cli_env):
    _invoke("kg", "bind-source", "support", "--database", "kgs", "--label", "KG_support")

    output = _invoke("kg", "source", "support")

    assert cli_env.get_graph_source("support") == GraphSourceScope(database="kgs", label="KG_support")
    assert "kgs" in output and "KG_support" in output


def test_cli_sets_and_shows_the_evolution_mode(cli_env):
    assert _invoke("kg", "evolution-mode", "support").strip() == "evolving"

    _invoke("kg", "evolution-mode", "support", "strict")

    assert cli_env.get_evolution_mode("support") == "strict"
    assert CliRunner().invoke(app, ["kg", "evolution-mode", "support", "loose"]).exit_code == 1


def _two_runs(sdk):
    sdk.bind_graph_source("support", GraphSourceScope(database="neo4j"))
    with sdk.start_run("support", ontology_version=1) as a:
        a.log_params({"llm": "gpt-x"})
    with sdk.start_run("support", ontology_version=1) as b:
        b.log_params({"llm": "claude"})
    return a.id, b.id


def test_cli_lists_gets_and_compares_runs(cli_env):
    a, b = _two_runs(cli_env)

    listed = _invoke("runs", "list", "support")
    fetched = _invoke("runs", "get", a)
    compared = _invoke("runs", "compare", a, b)

    assert [line.split()[0] for line in listed.strip().splitlines()[1:]] == [a, b]
    assert a in fetched and "Conformance" in fetched
    assert "gpt-x" in compared and "claude" in compared
    assert "conformance.score" in compared


def test_cli_evaluates_a_run_and_shows_its_evaluations(cli_env):
    a, _ = _two_runs(cli_env)

    evaluated = _invoke("runs", "evaluate", a)
    shown = _invoke("runs", "evaluations", a)

    for output in (evaluated, shown):
        assert "conformance" in output and "observed_schema" in output


def test_cli_lists_observations(cli_env):
    a, b = _two_runs(cli_env)

    output = _invoke("observations", "list", "support")

    runs = [line.split()[-1] for line in output.strip().splitlines()[1:]]
    assert runs == [a, b]


def test_cli_lists_gate_results(cli_env, tmp_path):
    config = tmp_path / "stetiq.yaml"
    config.write_text(
        yaml.safe_dump(
            {"gates": [{"name": "safe", "check": "ontology_diff", "max_classification": "additive"}]}
        )
    )
    _invoke("gate", "support", "--config", str(config))

    output = _invoke("gate-results", "support")

    assert "safe" in output and "PASS" in output


def test_cli_adds_a_competency_question(cli_env):
    _invoke(
        "use-case",
        "add-question",
        "support",
        "--id",
        "cq1",
        "--question",
        "Which customers opened tickets?",
        "--concept",
        "(Customer)-[OPENED]->(Ticket)",
    )

    [version] = cli_env.list_use_case_versions("support")
    [question] = version.use_case.competency_questions
    assert (question.id, question.concepts) == ("cq1", ("(Customer)-[OPENED]->(Ticket)",))
