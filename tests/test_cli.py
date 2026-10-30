"""CLI smoke tests: the CLI is a thin layer over the SDK, which is tested in depth."""

import sys

import yaml
from typer.testing import CliRunner

import stetiq
from stetiq.cli import app
from stetiq.graph_source import GraphSourceScope, InMemoryGraphSource


def test_cli_registers_lists_and_fetches_ontology_versions(tmp_path, monkeypatch, support_ontology):
    monkeypatch.setenv("STETIQ_TRACKING_URI", f"sqlite:///{tmp_path / 'stetiq.db'}")
    ontology = tmp_path / "ontology.yaml"
    ontology.write_text(support_ontology)
    evolved = tmp_path / "evolved.yaml"
    evolved.write_text(support_ontology.replace("type: DATE", "type: DATE\n        required: true"))
    runner = CliRunner()

    created = runner.invoke(app, ["kg", "create", "customer-support-kg", "--ontology", str(ontology)])
    registered = runner.invoke(app, ["ontology", "register", "customer-support-kg", str(evolved)])
    listed = runner.invoke(app, ["ontology", "list", "customer-support-kg"])
    fetched = runner.invoke(app, ["ontology", "get", "customer-support-kg", "1"])

    assert created.exit_code == 0, created.output
    assert registered.exit_code == 0, registered.output
    assert "2" in registered.output
    assert listed.exit_code == 0
    assert [line.split()[0] for line in listed.output.strip().splitlines()[1:]] == ["1", "2"]
    assert "registered" in listed.output
    assert yaml.safe_load(fetched.output)["patterns"] == [["Customer", "OPENED", "Ticket"]]


def test_cli_reports_malformed_ontology_and_exits_non_zero(tmp_path, monkeypatch):
    monkeypatch.setenv("STETIQ_TRACKING_URI", f"sqlite:///{tmp_path / 'stetiq.db'}")
    ontology = tmp_path / "ontology.yaml"
    ontology.write_text("node_types: [Customer, Customer]")

    result = CliRunner().invoke(app, ["kg", "create", "customer-support-kg", "--ontology", str(ontology)])

    assert result.exit_code == 1
    assert "Customer" in result.output


CUSTOM_EVALUATOR_MODULE = '''
from stetiq import Evaluation, OntologyVersionEvaluator

class NodeTypeCount(OntologyVersionEvaluator):
    name = "node_type_count"

    def evaluate(self, version):
        return Evaluation(metrics={"node_types": len(version.ontology.node_types)})
'''


def test_cli_shows_and_re_runs_evaluations_with_a_custom_evaluator(
    tmp_path, monkeypatch, support_ontology
):
    monkeypatch.setenv("STETIQ_TRACKING_URI", f"sqlite:///{tmp_path / 'stetiq.db'}")
    (tmp_path / "my_evaluators.py").write_text(CUSTOM_EVALUATOR_MODULE)
    monkeypatch.syspath_prepend(str(tmp_path))
    ontology = tmp_path / "ontology.yaml"
    ontology.write_text(support_ontology)
    runner = CliRunner()
    runner.invoke(app, ["kg", "create", "customer-support-kg", "--ontology", str(ontology)])

    shown = runner.invoke(app, ["ontology", "evaluations", "customer-support-kg", "1"])
    rerun = runner.invoke(
        app,
        ["ontology", "evaluate", "customer-support-kg", "1",
         "--evaluator", "my_evaluators:NodeTypeCount"],
    )

    assert shown.exit_code == 0, shown.output
    assert "isolated_node_types" in shown.output
    assert "max_depth" in shown.output
    assert rerun.exit_code == 0, rerun.output
    assert "node_type_count" in rerun.output
    assert "isolated_node_types" in rerun.output


def test_cli_diffs_two_ontology_versions(tmp_path, monkeypatch, support_ontology):
    monkeypatch.setenv("STETIQ_TRACKING_URI", f"sqlite:///{tmp_path / 'stetiq.db'}")
    ontology = tmp_path / "ontology.yaml"
    ontology.write_text(support_ontology)
    evolved = tmp_path / "evolved.yaml"
    evolved.write_text(support_ontology.replace("  - label: OPENED", "  - label: CLOSED").replace("OPENED", "CLOSED"))
    runner = CliRunner()
    runner.invoke(app, ["kg", "create", "customer-support-kg", "--ontology", str(ontology)])
    runner.invoke(app, ["ontology", "register", "customer-support-kg", str(evolved)])

    result = runner.invoke(app, ["ontology", "diff", "customer-support-kg", "1", "2"])
    unchanged = runner.invoke(app, ["ontology", "diff", "customer-support-kg", "1", "1"])

    assert result.exit_code == 0, result.output
    lines = [line.split()[:3] for line in result.output.strip().splitlines()]
    assert ["additive", "added", "CLOSED"] in lines
    assert ["breaking", "removed", "OPENED"] in lines
    assert "Overall: breaking" in result.output
    assert unchanged.exit_code == 0
    assert "No changes" in unchanged.output


def test_cli_registers_a_use_case_and_evaluates_answerability(tmp_path, monkeypatch, support_ontology):
    monkeypatch.setenv("STETIQ_TRACKING_URI", f"sqlite:///{tmp_path / 'stetiq.db'}")
    ontology = tmp_path / "ontology.yaml"
    ontology.write_text(support_ontology)
    use_case = tmp_path / "use-case.yaml"
    use_case.write_text(
        "competency_questions:\n"
        "  - {id: agents, question: 'Who handles tickets?', concepts: [Agent]}\n"
    )
    runner = CliRunner()
    runner.invoke(app, ["kg", "create", "kg", "--ontology", str(ontology)])

    registered = runner.invoke(app, ["use-case", "register", "kg", str(use_case)])
    listed = runner.invoke(app, ["use-case", "list", "kg"])
    fetched = runner.invoke(app, ["use-case", "get", "kg", "1"])
    evaluated = runner.invoke(app, ["ontology", "evaluate", "kg", "1", "--use-case-version", "1"])

    assert registered.exit_code == 0, registered.output
    assert "Use Case version 1" in registered.output
    assert [line.split()[0] for line in listed.output.strip().splitlines()[1:]] == ["1"]
    assert yaml.safe_load(fetched.output)["competency_questions"][0]["id"] == "agents"
    assert evaluated.exit_code == 0, evaluated.output
    assert "structural_answerability (Use Case version 1):" in evaluated.output
    assert "agents [unanswerable_questions]: missing Agent" in evaluated.output


def test_cli_moves_lists_and_fetches_aliases_with_an_audit_log(tmp_path, monkeypatch, support_ontology):
    monkeypatch.setenv("STETIQ_TRACKING_URI", f"sqlite:///{tmp_path / 'stetiq.db'}")
    ontology = tmp_path / "ontology.yaml"
    ontology.write_text(support_ontology)
    evolved = tmp_path / "evolved.yaml"
    evolved.write_text(support_ontology.replace("  - label: OPENED", "  - label: CLOSED").replace("OPENED", "CLOSED"))
    runner = CliRunner()
    runner.invoke(app, ["kg", "create", "kg", "--ontology", str(ontology)])
    runner.invoke(app, ["ontology", "register", "kg", str(evolved)])

    moved = runner.invoke(app, ["alias", "set", "kg", "staging", "2", "--actor", "ada"])
    promoted = runner.invoke(app, ["alias", "set", "kg", "production", "2", "--actor", "ada"])
    listed = runner.invoke(app, ["alias", "list", "kg"])
    fetched = runner.invoke(app, ["alias", "get", "kg", "production"])
    diffed = runner.invoke(app, ["ontology", "diff", "kg", "1"])  # BASE 1 -> latest
    rolled_back = runner.invoke(app, ["alias", "set", "kg", "production", "1", "--actor", "bob"])
    log = runner.invoke(app, ["alias", "log", "kg"])
    contract = runner.invoke(app, ["alias", "contract", "kg", "staging"])
    shown = runner.invoke(app, ["alias", "contract", "kg"])

    for result in (moved, promoted, listed, fetched, diffed, rolled_back, log, contract, shown):
        assert result.exit_code == 0, result.output
    assert [line.split()[:2] for line in listed.output.strip().splitlines()[1:]] == [
        ["production", "2"],
        ["staging", "2"],
    ]
    assert yaml.safe_load(fetched.output)["patterns"] == [["Customer", "CLOSED", "Ticket"]]
    assert "Overall: breaking" in diffed.output
    entries = [line.split()[:4] for line in log.output.strip().splitlines()[1:]]
    assert entries == [
        ["production", "-", "1", "stetiq"],
        ["staging", "-", "2", "ada"],
        ["production", "1", "2", "ada"],
        ["production", "2", "1", "bob"],
    ]
    assert shown.output.strip() == "staging"


def test_cli_reports_an_unknown_alias(tmp_path, monkeypatch, support_ontology):
    monkeypatch.setenv("STETIQ_TRACKING_URI", f"sqlite:///{tmp_path / 'stetiq.db'}")
    ontology = tmp_path / "ontology.yaml"
    ontology.write_text(support_ontology)
    CliRunner().invoke(app, ["kg", "create", "kg", "--ontology", str(ontology)])

    result = CliRunner().invoke(app, ["alias", "get", "kg", "nope"])

    assert result.exit_code == 1
    assert "nope" in result.output


# The user's pipeline for `stetiq run`: checks it got the Declared Ontology, exits with argv[2].
RUN_PIPELINE = """
import pathlib, sys, yaml
assert yaml.safe_load(pathlib.Path(sys.argv[1]).read_text())["patterns"] == [["Customer", "OPENED", "Ticket"]]
sys.exit(int(sys.argv[2]))
"""


def _repo_with_entry_point(tmp_path, monkeypatch, support_ontology, exit_code):
    uri = f"sqlite:///{tmp_path / 'stetiq.db'}"
    monkeypatch.setenv("STETIQ_TRACKING_URI", uri)
    # Plays STETIQ_GRAPH_SOURCE_URI pointing at the graph the pipeline wrote to.
    graph = InMemoryGraphSource()
    graph.add_node(["Customer"], {"name": "Ada"})
    monkeypatch.setattr("stetiq.client.graph_source_from_env", lambda: graph)
    sdk = stetiq.Client(uri, graph_source=graph)
    sdk.create_knowledge_graph("kg", ontology=support_ontology)
    sdk.bind_graph_source("kg", GraphSourceScope(database="neo4j"))

    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "pipeline.py").write_text(RUN_PIPELINE)
    (repo / "stetiq.yaml").write_text(
        yaml.safe_dump(
            {
                "knowledge_graph": "kg",
                "entry_point": {"command": [sys.executable, "pipeline.py", "{ontology}", str(exit_code)]},
            }
        )
    )
    return sdk, graph, repo


def test_cli_run_invokes_the_entry_point_and_exits_zero_when_the_run_finishes(
    tmp_path, monkeypatch, support_ontology
):
    sdk, _, repo = _repo_with_entry_point(tmp_path, monkeypatch, support_ontology, exit_code=0)
    monkeypatch.chdir(repo)  # default --config ./stetiq.yaml, default KG from it

    result = CliRunner().invoke(app, ["run"])

    assert result.exit_code == 0, result.output
    [run] = sdk.list_runs("kg")
    assert run.status == "finished"
    assert run.id in result.output
    assert "Conformance" in result.output


def test_cli_run_exits_non_zero_when_the_entry_point_fails(tmp_path, monkeypatch, support_ontology):
    sdk, _, repo = _repo_with_entry_point(tmp_path, monkeypatch, support_ontology, exit_code=2)

    result = CliRunner().invoke(app, ["run", "kg", "--config", str(repo / "stetiq.yaml")])

    assert result.exit_code == 1
    [run] = sdk.list_runs("kg")
    assert run.status == "failed"
    assert "exited with code 2" in result.output


def test_cli_run_exits_non_zero_when_strict_mode_fails_the_run(tmp_path, monkeypatch, support_ontology):
    sdk, graph, repo = _repo_with_entry_point(tmp_path, monkeypatch, support_ontology, exit_code=0)
    sdk.set_evolution_mode("kg", "strict")
    graph.add_node(["Agent"], {})

    result = CliRunner().invoke(app, ["run", "--config", str(repo / "stetiq.yaml"), "--ontology-version", "1"])

    assert result.exit_code == 1
    assert [r.status for r in sdk.list_runs("kg")] == ["failed"]
    assert "Agent" in result.output


def test_cli_run_reports_a_config_without_an_entry_point(tmp_path):
    config = tmp_path / "stetiq.yaml"
    config.write_text("gates: {}\n")

    result = CliRunner().invoke(app, ["run", "kg", "--config", str(config)])

    assert result.exit_code == 1
    assert "entry_point" in result.output
