"""CLI smoke tests: the CLI is a thin layer over the SDK, which is tested in depth."""

import yaml
from typer.testing import CliRunner

from stetiq.cli import app


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


GATES_CONFIG = """
knowledge_graph: kg
gates:
  - name: no-breaking-changes
    check: ontology_diff
    max_classification: deprecating
"""


def test_cli_gate_exits_non_zero_naming_the_failed_gates_and_why(tmp_path, monkeypatch, support_ontology):
    monkeypatch.setenv("STETIQ_TRACKING_URI", f"sqlite:///{tmp_path / 'stetiq.db'}")
    monkeypatch.chdir(tmp_path)
    (tmp_path / "stetiq.yaml").write_text(GATES_CONFIG)
    ontology = tmp_path / "ontology.yaml"
    ontology.write_text(support_ontology)
    evolved = tmp_path / "evolved.yaml"
    evolved.write_text(support_ontology.replace("  - label: OPENED", "  - label: CLOSED").replace("OPENED", "CLOSED"))
    runner = CliRunner()
    runner.invoke(app, ["kg", "create", "kg", "--ontology", str(ontology)])

    passing = runner.invoke(app, ["gate", "--version", "1"])  # KG from the config file
    runner.invoke(app, ["ontology", "register", "kg", str(evolved)])
    failing = runner.invoke(app, ["gate", "kg"])  # latest version, ./stetiq.yaml
    promoted = runner.invoke(app, ["alias", "set", "kg", "production", "2", "--actor", "ada"])
    log = runner.invoke(app, ["alias", "log", "kg"])

    assert passing.exit_code == 0, passing.output
    assert "PASS  no-breaking-changes" in passing.output
    assert failing.exit_code == 1, failing.output
    assert "FAIL  no-breaking-changes" in failing.output
    assert "breaking change (v1 -> v2): removed OPENED" in failing.output
    assert "1 of 1 Gates failed" in failing.output
    assert promoted.exit_code == 0
    assert log.output.strip().splitlines()[-1].split()[:5] == ["production", "1", "2", "ada", "failed"]


def test_cli_gate_reports_a_malformed_config_file(tmp_path, monkeypatch, support_ontology):
    monkeypatch.setenv("STETIQ_TRACKING_URI", f"sqlite:///{tmp_path / 'stetiq.db'}")
    ontology = tmp_path / "ontology.yaml"
    ontology.write_text(support_ontology)
    config = tmp_path / "gates.yaml"
    config.write_text("gates: [{check: nope}]")
    CliRunner().invoke(app, ["kg", "create", "kg", "--ontology", str(ontology)])

    result = CliRunner().invoke(app, ["gate", "kg", "--config", str(config)])
    missing = CliRunner().invoke(app, ["gate", "kg", "--config", str(tmp_path / "absent.yaml")])

    assert result.exit_code == 1
    assert "nope" in result.output
    assert missing.exit_code == 1
    assert "absent.yaml" in missing.output
