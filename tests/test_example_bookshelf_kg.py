"""The town library example (examples/bookshelf-kg), stetiq's smallest walkthrough, runs
end to end, offline, and tells the story its README promises: declare, hierarchy,
deprecate, build, promote and roll back.

It drives the SDK in local mode over a temporary SQLite tracking database and the
in-memory Graph Source the demo fills from data/."""

import importlib.util
import sys
from pathlib import Path

import pytest

EXAMPLE_DIR = Path(__file__).resolve().parent.parent / "examples" / "bookshelf-kg"
# Sibling examples each have a demo.py and share this pytest process: load this one
# under its own module name, never as plain "demo".
MODULE_NAME = "example_bookshelf_kg_demo"


@pytest.fixture(scope="module")
def demo(tmp_path_factory):
    workspace = tmp_path_factory.mktemp("bookshelf-kg")
    spec = importlib.util.spec_from_file_location(MODULE_NAME, EXAMPLE_DIR / "demo.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[MODULE_NAME] = module
    sys.path.insert(0, str(EXAMPLE_DIR))
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path.remove(str(EXAMPLE_DIR))
    return module.run_demo(tracking_uri=f"sqlite:///{workspace / 'stetiq.db'}", quiet=True)


KG = "town-library"


def result(results, evaluator):
    [found] = [r for r in results if r.evaluator == evaluator]
    return found


def test_registering_the_same_yaml_twice_returns_the_same_version(demo):
    first = demo.client.get_ontology_version(KG, 1)
    assert demo.v1_again.number == 1
    assert demo.v1_again.content_hash == first.content_hash
    # Four versions in the end, every one registered by hand: no run yielded a Candidate.
    versions = demo.client.list_ontology_versions(KG)
    assert [(v.number, v.origin) for v in versions] == [
        (1, "registered"),
        (2, "registered"),
        (3, "registered"),
        (4, "registered"),
    ]


def test_the_file_diff_is_breaking_and_v2_introduces_a_two_level_hierarchy(demo):
    # Compared before registering: lifting `name` from Author to Person removes a property.
    assert demo.file_diff.classification == "breaking"
    assert ("Author.name", "removed") in {(c.concept, str(c.kind)) for c in demo.file_diff.changes}

    hierarchy = result(demo.client.get_evaluation_results(KG, 2), "hierarchy")
    assert hierarchy.metrics["max_depth"] == 2
    assert hierarchy.metrics["root_node_types"] == 5
    assert hierarchy.metrics["max_children"] == 2
    assert result(demo.client.get_evaluation_results(KG, 3), "hierarchy").metrics == {
        "max_depth": 2,
        "max_breadth": 6,
        "root_node_types": 6,
        "max_children": 2,
    }


def test_the_duplicate_constraint_is_inherited_in_v2_and_fixed_in_v3(demo):
    v2 = result(demo.client.get_evaluation_results(KG, 2), "constraint_consistency")
    assert v2.metrics["inconsistencies"] == 1
    assert v2.metrics["inherited_duplicate_constraints"] == 1
    [detail] = v2.details
    assert (detail.item, detail.message) == ("Author.name", "already unique via Person")
    v3 = result(demo.client.get_evaluation_results(KG, 3), "constraint_consistency")
    assert v3.metrics["inconsistencies"] == 0


def test_deprecating_genre_is_deprecating_but_removing_it_is_breaking(demo):
    assert demo.diff_v2_v3.classification == "deprecating"
    assert {c.concept for c in demo.diff_v2_v3.deprecating} == {"Genre", "IN_GENRE"}
    assert {c.concept for c in demo.diff_v2_v3.additive} == {
        "Subject",
        "HAS_SUBJECT",
        "Author.name",
    }
    assert demo.diff_v3_v4.classification == "breaking"
    assert [(c.concept, str(c.kind)) for c in demo.diff_v3_v4.changes] == [
        ("Genre", "removed"),
        ("IN_GENRE", "removed"),
    ]


def test_the_single_construction_run_conforms_to_v3_without_a_candidate(demo):
    run = demo.run
    assert run.status == "finished"
    assert run.ontology_version == 3
    assert run.conformance.score == 1.0
    assert run.conformance.mismatches == ()
    assert run.candidate_version is None
    assert run.params["as_of"] == "2026-10-30"
    assert run.metrics == {"books": 7, "loans": 12, "nodes": 41, "relationships": 58}

    results = demo.client.get_run_evaluation_results(run.id)
    assert result(results, "competency_question_execution").metrics == {
        "questions": 4,
        "passed_questions": 4,
        "failed_questions": 0,
        "skipped_questions": 2,
        "pass_ratio": 1.0,
    }
    [overdue] = [
        d
        for d in result(results, "competency_question_execution").details
        if d.item == "overdue-loans"
    ]
    assert overdue.data == {"status": "passed", "rows": 3, "check": "expected_answer"}
    # Aggregates only reach stetiq (ADR 0001): the Observed Schema counts the leaf labels.
    observed = result(results, "observed_schema")
    assert observed.metrics["nodes"] == 41
    assert observed.metrics["relationships"] == 58
    counts = {d.item: d.data["count"] for d in observed.details if "count" in d.data}
    assert counts["Person"] == 2 and counts["Author"] == 6 and counts["Member"] == 4


def test_structural_answerability_grows_from_v1_to_v3(demo):
    v1 = result(demo.client.get_evaluation_results(KG, 1), "structural_answerability")
    assert v1.metrics["answerable_questions"] == 1
    assert v1.metrics["answerable_ratio"] == pytest.approx(1 / 6)
    statuses = {d.item: d.data["status"] for d in v1.details}
    assert statuses == {
        "books-per-author": "answerable",
        "overdue-loans": "unanswerable",
        "members-per-branch": "unanswerable",
        "popular-books": "unanswerable",
        "books-by-subject": "unanswerable",
        "authors-who-are-members": "unmapped",
    }
    v3 = result(demo.client.get_evaluation_results(KG, 3), "structural_answerability")
    assert v3.metrics["answerable_questions"] == 5
    assert v3.metrics["answerable_ratio"] == pytest.approx(5 / 6)
    assert {d.item for d in v3.details if d.data["status"] != "answerable"} == {
        "authors-who-are-members"
    }
    # Hierarchy-aware: `a.name` on Author is satisfied by Person.name.
    [books_per_author] = [d for d in v3.details if d.item == "books-per-author"]
    assert books_per_author.data["missing"] == []


def test_the_gates_reject_v2_and_v4_and_accept_v3(demo):
    assert {o.gate.name for o in demo.gates_v2.failed} == {
        "graph-conforms",
        "consistent-constraints",
        "questions-answerable",
    }
    assert demo.gates_v3.passed
    assert {o.gate.name for o in demo.gates_v4.failed} == {"no-breaking-changes", "graph-conforms"}
    [diff_gate] = [o for o in demo.gates_v4.outcomes if o.gate.name == "no-breaking-changes"]
    assert all("breaking change (v3 -> v4)" in reason for reason in diff_gate.reasons)
    assert len(diff_gate.reasons) == 2


def test_the_audit_log_records_promotion_and_rollback(demo):
    assert [
        (p.alias, p.from_version, p.to_version, p.actor, p.gate_result) for p in demo.promotions
    ] == [
        ("production", None, 1, "stetiq", None),
        ("production", 1, 2, "ines.ferreira", None),
        ("staging", None, 3, "ines.ferreira", "passed"),
        ("production", 2, 3, "ines.ferreira", "passed"),
        ("production", 3, 2, "ines.ferreira", "failed"),
    ]
    assert demo.client.get_contract_version(KG).number == 2
    assert demo.client.get_alias(KG, "staging").version == 3
    assert demo.client.get_evolution_mode(KG) == "evolving"
