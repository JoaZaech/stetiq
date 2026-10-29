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
