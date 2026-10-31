"""The citation graph example (examples/citation-graph-kg) runs end to end, offline, and
tells the story its README promises: a stetiq server with API Tokens for three teams, a
Use Case that grows while the Ontology catches up, a duplicate-author Gate that the loader
has to earn, and an audit log that names the token's user.

It drives the SDK in remote mode against an in-process FastAPI server over a temporary
SQLite database, exactly like the `remote` tracking mode in conftest.py, with the
example's file-backed `ScholarGraph` as the Graph Source."""

import importlib.util
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import stetiq
from stetiq.server import create_app

EXAMPLE_DIR = Path(__file__).resolve().parent.parent / "examples" / "citation-graph-kg"
MODULE_NAME = "example_citation_graph_kg_demo"
KG = "scholar-kg"


def _load_demo_module():
    """Load the example's demo.py under a unique module name: sibling examples all have
    a demo.py, and they share this pytest process."""
    spec = importlib.util.spec_from_file_location(MODULE_NAME, EXAMPLE_DIR / "demo.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[MODULE_NAME] = module
    sys.path.insert(0, str(EXAMPLE_DIR))
    try:
        spec.loader.exec_module(module)
    finally:
        while str(EXAMPLE_DIR) in sys.path:
            sys.path.remove(str(EXAMPLE_DIR))
    return module


@pytest.fixture(scope="module")
def demo(tmp_path_factory):
    workspace = tmp_path_factory.mktemp("citation-graph-kg")
    database_url = f"sqlite:///{workspace / 'server.db'}"
    module = _load_demo_module()
    # The test owns the server, the way conftest's remote mode does; the demo only
    # talks to it over HTTP with the tokens it mints against the same database.
    with TestClient(create_app(database_url=database_url)) as http:
        yield module.run_demo(
            tracking_uri=database_url,
            graph_file=workspace / "scholar.json",
            http=http,
            quiet=True,
        )


def result(results, evaluator):
    [found] = [r for r in results if r.evaluator == evaluator]
    return found


def test_a_read_token_lists_versions_but_cannot_register_one(demo):
    assert [v.number for v in demo.library.list_ontology_versions(KG)] == [1, 2, 3, 4, 5]
    with pytest.raises(stetiq.PermissionDeniedError) as denied:
        demo.library.register_ontology(KG, EXAMPLE_DIR / "ontology" / "v3.yaml")
    assert "library" in str(denied.value) and "edit" in str(denied.value)
    assert demo.library_denied == str(denied.value)


def test_a_run_outside_the_tokens_grants_answers_like_an_unknown_run(demo):
    # A uniform 404: the events team's token cannot tell a real run id from a made-up one.
    with pytest.raises(stetiq.NotFoundError) as real:
        demo.outsider.get_run(demo.run1.id)
    unknown_id = sys.modules[MODULE_NAME].UNKNOWN_RUN_ID
    with pytest.raises(stetiq.NotFoundError) as unknown:
        demo.outsider.get_run(unknown_id)
    assert str(real.value).replace(demo.run1.id, unknown_id) == str(unknown.value)
    assert demo.outsider_errors["get_run(<run 1>)"].startswith("NotFoundError")
    # The Knowledge Graph's name is already in the URL, so that one is a plain denial.
    with pytest.raises(stetiq.PermissionDeniedError):
        demo.outsider.get_knowledge_graph(KG)
    # And its own grants work: the token itself is fine.
    assert demo.outsider.list_knowledge_graphs() == []


def test_the_first_run_observes_the_orcid_sync_and_registers_a_candidate(demo):
    run = demo.run1
    assert run.status == "finished"
    assert run.ontology_version == 1
    assert run.params["orcid_matching"] == "by-name"
    assert run.metrics["nodes"] == 204
    assert run.metrics["relationships"] == 400
    assert run.conformance.score == pytest.approx(11 / 12)
    assert {(str(m.kind), m.subject) for m in run.conformance.mismatches} == {
        ("undeclared", "Author.orcid"),
        ("undeclared", "Grant.funder"),
    }
    assert run.candidate_version == 2
    assert demo.office.get_ontology_version(KG, 2).origin == "run"

    results = demo.office.get_run_evaluation_results(run.id)
    assert result(results, "competency_question_execution").metrics["pass_ratio"] == 1.0
    dedupe = result(results, "author_dedupe").metrics
    assert dedupe == {"authors": 122, "duplicate_groups": 2, "duplicate_authors": 2}

    gates = demo.gates_candidate
    assert gates.ontology_version == 2
    assert {o.gate.name for o in gates.failed} == {"graph-conforms", "no-duplicate-authors"}


def test_each_use_case_version_is_judged_against_the_latest_ontology_version(demo):
    versions = demo.office.list_use_case_versions(KG)
    assert [(u.number, len(u.use_case.competency_questions)) for u in versions] == [
        (1, 5),
        (2, 6),
        (3, 7),
    ]
    # (Ontology Version, Use Case Version, answerable, questions) in story order:
    # registration judges the latest Ontology Version only (the Candidate v2 at the
    # time), v1 keeps its old verdict until re-judged, v3 answers everything, and the
    # CITES rename (v5) loses two questions.
    assert demo.answerability == [
        (1, 1, 5, 5),
        (2, 2, 6, 6),
        (2, 3, 6, 7),
        (1, 3, 5, 7),
        (3, 3, 7, 7),
        (5, 3, 5, 7),
    ]
    v1 = result(demo.office.get_evaluation_results(KG, 1), "structural_answerability")
    assert v1.use_case_version == 3
    statuses = {d.item: d.data["status"] for d in v1.details}
    assert statuses["self-citation-share"] == "unanswerable"
    assert statuses["orcid-coauthors"] == "unanswerable"
    assert statuses["most-cited-paper"] == "answerable"


def consumers_of(use_case_version):
    return {
        c.id: (c.name, c.kind, {t.id: set(t.competency_questions) for t in c.tasks})
        for c in use_case_version.use_case.consumers
    }


def test_the_use_case_names_the_consumers_and_the_tasks_they_need_answered(demo):
    # The two questions added later keep the Consumers of Use Case Version 1 and serve no
    # Task yet, nor does venues-by-year; papers-per-author and grant-funded-papers each
    # serve two Tasks.
    expected = {
        "research-portal": (
            "Research portal",
            "dashboard",
            {"researcher-profiles": {"papers-per-author", "co-authorship-pairs"}},
        ),
        "funder-report": (
            "Annual funder report",
            "report",
            {"report-grant-output": {"grant-funded-papers", "papers-per-author"}},
        ),
        "impact-assistant": (
            "Impact case assistant",
            "agent",
            {"draft-impact-case": {"most-cited-paper", "grant-funded-papers"}},
        ),
    }
    for number in (1, 2, 3):
        assert consumers_of(demo.office.get_use_case_version(KG, number)) == expected


def test_full_conformance_is_not_enough_until_the_loader_merges_by_orcid(demo):
    client = demo.office
    diff = client.diff_ontology_versions(KG, 1, 3)
    assert diff.classification == "additive"
    assert len(diff.changes) == 3

    assert demo.run2.conformance.score == 1.0
    assert demo.run2.candidate_version is None
    execution = result(
        client.get_run_evaluation_results(demo.run2.id), "competency_question_execution"
    )
    assert execution.metrics == {
        "questions": 7,
        "passed_questions": 7,
        "failed_questions": 0,
        "skipped_questions": 0,
        "pass_ratio": 1.0,
    }
    assert {o.gate.name for o in demo.gates_run2.failed} == {"no-duplicate-authors"}

    nightly = demo.nightly
    assert nightly.status == "finished"
    assert nightly.params["entry_point.exit_code"] == "0"
    assert nightly.conformance.score == 1.0
    dedupe = result(client.get_run_evaluation_results(nightly.id), "author_dedupe").metrics
    assert dedupe == {"authors": 120, "duplicate_groups": 0, "duplicate_authors": 0}
    assert demo.gates_nightly.passed
    assert [o.gate.name for o in demo.gates_nightly.outcomes] == [
        "no-breaking-changes",
        "graph-conforms",
        "no-duplicate-authors",
        "questions-answerable",
        "no-isolated-node-types",
        "no-orphans",
    ]


def test_promotions_record_the_tokens_user_not_the_clients_actor(demo):
    assert demo.ci.actor == "someone-else"
    promotions = demo.library.list_promotions(KG)
    assert [
        (p.alias, p.from_version, p.to_version, p.actor, p.gate_result) for p in promotions
    ] == [
        ("production", None, 1, "stetiq", None),
        ("production", 1, 3, "ci-bot", "passed"),
        ("staging", None, 4, "research-office", "passed"),
    ]
    assert demo.office.get_contract_version(KG).number == 3


def test_the_venue_hierarchy_is_additive_and_passes(demo):
    ontology = EXAMPLE_DIR / "ontology"
    diff = demo.library.diff_ontologies(
        ontology / "v3.yaml", ontology / "proposal-venue-hierarchy.yaml"
    )
    assert diff.classification == "additive"
    v4 = demo.office.get_ontology_version(KG, 4)
    assert {n.label for n in v4.ontology.node_types if n.parent == "Venue"} == {
        "Journal",
        "Conference",
    }
    assert demo.trial_run.ontology_version == 4
    assert demo.trial_run.conformance.score == 1.0
    assert demo.gates_venues.ontology_version == 4
    assert demo.gates_venues.passed
    assert demo.office.get_alias(KG, "staging").version == 4


def test_renaming_cites_is_breaking_and_fails_the_gates(demo):
    gates = demo.gates_rename
    assert gates.ontology_version == 5
    assert {o.gate.name for o in gates.failed} == {
        "no-breaking-changes",
        "graph-conforms",
        "no-duplicate-authors",
        "questions-answerable",
    }
    [diff_gate] = [o for o in gates.outcomes if o.gate.name == "no-breaking-changes"]
    assert any("CITES" in reason and "breaking" in reason for reason in diff_gate.reasons)
    [answerable] = [o for o in gates.outcomes if o.gate.name == "questions-answerable"]
    assert any("0.714" in reason for reason in answerable.reasons)
    # Production stays where the CI bot's Promotion put it.
    assert demo.office.get_contract_version(KG).number == 3
    assert demo.office.get_evolution_mode(KG) == "evolving"
