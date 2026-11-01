"""The clinical-trials registry example (examples/clinical-trials-kg) runs end to end,
offline, and tells the story its README promises: a regulated Knowledge Graph in strict
Evolution Mode from day one, governed by hand-registered Ontology Versions, aligned with
a gold reference, and promoted by a bot only once every Gate passes.

It drives the SDK in local mode over a temporary SQLite tracking database and the
example's file-backed graph database, reading the committed registry exports."""

import importlib.util
import sys
from pathlib import Path

import pytest

EXAMPLE_DIR = Path(__file__).resolve().parent.parent / "examples" / "clinical-trials-kg"
MODULE_NAME = "example_clinical_trials_kg_demo"


@pytest.fixture(scope="module")
def demo(tmp_path_factory):
    workspace = tmp_path_factory.mktemp("clinical-trials-kg")
    spec = importlib.util.spec_from_file_location(MODULE_NAME, EXAMPLE_DIR / "demo.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[MODULE_NAME] = module  # dataclasses need the module importable by name
    sys.path.insert(0, str(EXAMPLE_DIR))
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path.remove(str(EXAMPLE_DIR))
    return module.run_demo(
        tracking_uri=f"sqlite:///{workspace / 'stetiq.db'}",
        graph_file=workspace / "registry.json",
        quiet=True,
    )


KG = "trial-registry"
GOLD = {"reference_knowledge_graph": "trial-registry-gold", "reference_version": 1}


def result(results, evaluator):
    [found] = [r for r in results if r.evaluator == evaluator]
    return found


def undeclared(run):
    return {m.subject for m in run.conformance.mismatches if str(m.kind) == "undeclared"}


def consumers_of(use_case_version):
    return {
        c.id: (c.name, c.kind, {t.id: set(t.competency_questions) for t in c.tasks})
        for c in use_case_version.use_case.consumers
    }


def test_the_use_case_names_the_consumers_and_the_tasks_they_need_answered(demo):
    # serious-events-per-trial, events-per-arm and protocol-deviations each serve two
    # Tasks; consent-withdrawals serves none yet.
    latest = demo.dana.get_use_case_version(KG)
    assert latest.number == 1
    assert consumers_of(latest) == {
        "safety-signal-agent": (
            "Safety signal agent",
            "agent",
            {"screen-safety-signals": {"serious-events-per-trial", "events-per-arm"}},
        ),
        "dsmb": (
            "Data Safety Monitoring Board",
            "team",
            {
                "quarterly-safety-review": {
                    "serious-events-per-trial",
                    "events-per-arm",
                    "protocol-deviations",
                }
            },
        ),
        "site-monitoring-dashboard": (
            "Site monitoring dashboard",
            "dashboard",
            {
                "plan-site-visits": {
                    "participants-per-site",
                    "site-investigators",
                    "protocol-deviations",
                }
            },
        ),
        "portfolio-report": (
            "Trial portfolio report",
            "report",
            {"summarise-portfolio": {"drugs-under-test", "conditions-studied"}},
        ),
    }


def test_the_registry_is_strict_from_day_one_and_v1_lacks_the_arm_concepts(demo):
    client = demo.dana
    assert client.get_evolution_mode(KG) == "strict"
    answerability = result(client.get_evaluation_results(KG, 1), "structural_answerability")
    assert answerability.metrics["questions"] == 8
    assert answerability.metrics["answerable_questions"] == 6
    assert answerability.metrics["answerable_ratio"] == pytest.approx(0.75)
    statuses = {d.item: d.data["status"] for d in answerability.details}
    assert statuses["events-per-arm"] == "unanswerable"
    assert statuses["consent-withdrawals"] == "unmapped"
    assert statuses["drugs-under-test"] == "answerable"  # Drug through the hierarchy


def test_the_first_run_fails_in_strict_mode_and_nothing_enters_the_ontology(demo):
    run = demo.run1
    assert run.status == "failed"
    assert run.ontology_version == 1
    assert run.candidate_version is None
    assert run.conformance.score == pytest.approx(59 / 66)
    assert undeclared(run) == {
        "Arm",
        "Arm.code",
        "Arm.kind",
        "ASSIGNED_TO",
        "EXPERIENCED",
        "(Participant)-[ASSIGNED_TO]->(Arm)",
        "(Participant)-[EXPERIENCED]->(AdverseEvent)",
    }
    # Strict mode never yields a Candidate: every version was registered by a human.
    assert [(v.number, v.origin) for v in demo.dana.list_ontology_versions(KG)] == [
        (1, "registered"),
        (2, "registered"),
        (3, "registered"),
        (4, "registered"),
    ]
    coverage = result(demo.dana.get_run_evaluation_results(run.id), "consent_coverage")
    assert coverage.metrics == {
        "participants": 150,
        "without_consent": 4,
        "coverage": pytest.approx(146 / 150),
    }


def test_the_governed_v2_is_additive_and_the_graph_conforms_to_it(demo):
    client = demo.dana
    diff = client.diff_ontology_versions(KG, 1, 2)
    assert diff.classification == "additive"
    assert {(str(c.kind), c.concept) for c in diff.changes} == {
        ("added", "Arm"),
        ("added", "ASSIGNED_TO"),
        ("added", "EXPERIENCED"),
    }
    answerability = result(client.get_evaluation_results(KG, 2), "structural_answerability")
    assert answerability.metrics["answerable_questions"] == 7
    assert answerability.metrics["unmapped_questions"] == 1

    run = demo.run2
    assert run.status == "finished"
    assert run.ontology_version == 2
    assert run.conformance.score == 1.0
    execution = result(client.get_run_evaluation_results(run.id), "competency_question_execution")
    assert execution.metrics == {
        "questions": 7,
        "passed_questions": 7,
        "failed_questions": 0,
        "skipped_questions": 1,
        "pass_ratio": 1.0,
    }


def test_v2_fails_the_gold_consent_and_constraint_gates(demo):
    client = demo.dana
    results = client.get_evaluation_results(KG, 2)
    gold = result(results, "gold_alignment")
    assert gold.parameters == GOLD
    assert gold.metrics["precision"] == pytest.approx(46 / 47)
    assert gold.metrics["recall"] == pytest.approx(46 / 55)
    missing = {d.item for d in gold.details if d.metric == "unmatched_reference_concepts"}
    assert {"Site.country", "Visit.window_days", "Trial.status", "Sponsor"} <= missing

    constraints = result(results, "constraint_consistency")
    assert constraints.metrics["inconsistencies"] == 1
    assert [d.item for d in constraints.details] == ["Investigator.orcid"]
    assert result(results, "pii_free").metrics["pii_properties"] == 0

    gates = demo.gates_v2
    assert gates.ontology_version == 2
    assert {o.gate.name for o in gates.failed} == {
        "gold-aligned",
        "consent-covered",
        "consistent-constraints",
    }


def test_v3_passes_every_gate_and_the_bot_promotes_production(demo):
    client = demo.dana
    assert client.diff_ontology_versions(KG, 1, 3).classification == "additive"

    run = demo.run3
    assert run.status == "finished"
    assert run.ontology_version == 3
    assert run.params["entry_point.exit_code"] == "0"
    assert run.conformance.score == 1.0
    coverage = result(client.get_run_evaluation_results(run.id), "consent_coverage")
    assert coverage.metrics["coverage"] == 1.0

    gold = result(client.get_evaluation_results(KG, 3), "gold_alignment")
    assert gold.metrics["precision"] == pytest.approx(49 / 50)
    assert gold.metrics["recall"] == pytest.approx(49 / 55)

    comparison = client.compare_runs([demo.run1.id, demo.run2.id, run.id])
    assert comparison.ontology_versions == (1, 2, 3)
    assert comparison.evaluations["consent_coverage.coverage"] == pytest.approx(
        (146 / 150, 146 / 150, 1.0)
    )

    assert demo.gates_v3.passed
    assert client.get_contract_version(KG).number == 3
    assert [
        (p.alias, p.from_version, p.to_version, p.actor, p.gate_result)
        for p in client.list_promotions(KG)
    ] == [
        ("production", None, 1, "stetiq", None),
        ("staging", None, 3, "dana.reyes", "passed"),
        ("production", 1, 3, "cdm-bot", "passed"),
    ]


def test_an_observation_between_runs_finds_no_drift(demo):
    assert demo.drift is None
    assert demo.dana.list_drift_events(KG) == []


def test_an_undeclared_biomarker_feed_fails_the_nightly_run(demo):
    run = demo.biomarker_run
    assert run.status == "failed"
    assert run.ontology_version == 3
    assert run.candidate_version is None
    assert {"Biomarker", "Biomarker.assay", "MEASURES"} <= undeclared(run)
    assert demo.dana.get_contract_version(KG).number == 3


def test_the_merge_sites_proposal_is_breaking_and_leaks_personal_data(demo):
    gates = demo.gates_proposal
    assert gates.ontology_version == 4
    outcomes = {o.gate.name: o for o in gates.outcomes}
    assert not outcomes["no-breaking-changes"].passed
    assert any(
        "Site" in reason and "breaking" in reason
        for reason in outcomes["no-breaking-changes"].reasons
    )
    assert not outcomes["pii-free"].passed
    assert any("Participant.dob" in reason for reason in outcomes["pii-free"].reasons)
    assert demo.dana.get_contract_version(KG).number == 3
    assert demo.dana.get_evolution_mode(KG) == "strict"
