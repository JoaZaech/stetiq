"""The retail orders example (examples/retail-orders-kg), stetiq's large, operations-side
walkthrough, runs end to end, offline, and tells the story its README promises: six
Construction Runs compared, a Candidate adopted as a new version, Gates and Promotion, then
a season of weekly Observations with statistical and structural Drift.

It drives the SDK in local mode over a temporary SQLite tracking database and the example's
label-scoped in-memory Graph Source, generated from a fixed seed."""

import importlib.util
import sys
from pathlib import Path

import pytest

EXAMPLE_DIR = Path(__file__).resolve().parent.parent / "examples" / "retail-orders-kg"
# Sibling examples each have a demo.py and share this pytest process: load this one under
# its own module name, never as plain "demo".
MODULE_NAME = "example_retail_orders_kg_demo"


@pytest.fixture(scope="module")
def demo(tmp_path_factory):
    workspace = tmp_path_factory.mktemp("retail-orders-kg")
    spec = importlib.util.spec_from_file_location(MODULE_NAME, EXAMPLE_DIR / "demo.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[MODULE_NAME] = module
    sys.path.insert(0, str(EXAMPLE_DIR))
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path.remove(str(EXAMPLE_DIR))
    demo = module.run_demo(tracking_uri=f"sqlite:///{workspace / 'stetiq.db'}", quiet=True)
    demo.db_file = workspace / "stetiq.db"
    return demo


KG = "retail-orders"


def result(results, evaluator):
    [found] = [r for r in results if r.evaluator == evaluator]
    return found


def consumers_of(use_case_version):
    return {
        c.id: (c.name, c.kind, {t.id: set(t.competency_questions) for t in c.tasks})
        for c in use_case_version.use_case.consumers
    }


def test_the_use_case_names_the_consumers_and_the_tasks_they_need_answered(demo):
    # top-categories-by-revenue serves two Tasks; basket-affinity serves none yet.
    latest = demo.mara.get_use_case_version(KG)
    assert latest.number == 1
    assert consumers_of(latest) == {
        "analytics-dashboard": (
            "Sales analytics dashboard",
            "dashboard",
            {
                "weekly-sales-review": {
                    "top-categories-by-revenue",
                    "lines-per-order",
                    "repeat-customers",
                },
                "returns-watch": {"return-rate-per-product"},
            },
        ),
        "supplier-risk-report": (
            "Supplier risk report",
            "report",
            {"supplier-concentration": {"suppliers-behind-orders", "orders-per-warehouse"}},
        ),
        "merchandising-team": (
            "Merchandising",
            "team",
            {"plan-category-pages": {"category-tree-depth", "top-categories-by-revenue"}},
        ),
    }


def test_v1_answers_six_of_eight_questions_with_a_two_level_hierarchy(demo):
    results = demo.mara.get_evaluation_results(KG, 1)
    answerability = result(results, "structural_answerability")
    assert answerability.metrics["questions"] == 8
    assert answerability.metrics["answerable_questions"] == 6
    assert answerability.metrics["answerable_ratio"] == 0.75
    statuses = {d.item: d.data["status"] for d in answerability.details}
    assert statuses["return-rate-per-product"] == "unanswerable"
    assert statuses["basket-affinity"] == "unmapped"
    assert statuses["category-tree-depth"] == "answerable"
    assert result(results, "hierarchy").metrics["max_depth"] == 2
    v1 = demo.mara.get_ontology_version(KG, 1).ontology
    assert (len(v1.node_types), len(v1.relationship_types)) == (9, 8)


def test_six_runs_compared_the_fuzzy_runs_conform_best(demo):
    runs = demo.runs
    assert len(runs) == 6
    assert all(r.status == "finished" for r in runs)
    comparison = demo.comparison
    assert comparison.ontology_versions == (1, 1, 1, 1, 1, 3)
    assert comparison.params["dedupe_strategy"] == (
        "none",
        "none",
        "exact",
        "fuzzy",
        "fuzzy",
        "fuzzy",
    )
    assert comparison.params["include_returns"] == ("False",) * 4 + ("True",) * 2
    assert comparison.metrics["customers"] == (1100, 1100, 1040, 894, 894, 894)
    assert comparison.metrics["duplicate_customers_merged"] == (0, 0, 60, 206, 206, 206)
    assert comparison.metrics["orders"] == (2800,) * 6
    assert comparison.metrics["order_lines"] == (6375,) * 6
    # v1 has 59 checked items (node types, properties incl. Department's inherited ones,
    # relationship types, patterns); a run observing Return adds 7 more.
    scores = [c.score for c in comparison.conformance]
    assert scores == pytest.approx([49 / 59, 58 / 59, 58 / 59, 1.0, 59 / 66, 1.0])
    assert [i + 1 for i, s in enumerate(scores) if s == 1.0] == [4, 6]
    assert comparison.evaluations["competency_question_execution.pass_ratio"] == pytest.approx(
        [5 / 7, 6 / 7, 6 / 7, 6 / 7, 1.0, 1.0]
    )
    assert comparison.evaluations["observed_schema.nodes"][0] == 10404
    assert comparison.evaluations["observed_schema.nodes"][5] == 13047

    # Run 1: the shipments loader is off; run 2: duplicate guests have no email.
    assert {(str(m.kind), m.subject) for m in runs[0].conformance.mismatches} >= {
        ("absent", "Shipment"),
        ("absent", "SHIPPED_FROM"),
        ("absent", "FULFILLS"),
        ("required_missing", "Customer.email"),
    }
    assert [(str(m.kind), m.subject) for m in runs[1].conformance.mismatches] == [
        ("required_missing", "Customer.email")
    ]
    failed = {
        d.item
        for d in result(
            demo.mara.get_run_evaluation_results(runs[0].id), "competency_question_execution"
        ).details
        if d.data["status"] != "passed"
    }
    assert failed == {"orders-per-warehouse", "return-rate-per-product"}


def test_the_returns_run_yields_a_candidate_adopted_as_a_new_version(demo):
    run5 = demo.runs[4]
    assert {m.subject for m in run5.conformance.undeclared} == {
        "Return",
        "Return.id",
        "Return.reason",
        "Return.refund",
        "Return.returned_at",
        "RETURNED",
    }
    assert run5.candidate_version == 2
    assert demo.candidate.number == 2
    assert demo.candidate.origin == "run"
    assert demo.mara.diff_ontology_versions(KG, 1, 2).classification == "additive"
    # Adopting the Candidate with descriptions is a new version, not a dedupe hit.
    assert (demo.v3.number, demo.v3.origin) == (3, "registered")
    descriptions = demo.mara.diff_ontology_versions(KG, 2, 3)
    assert descriptions.classification == "cosmetic"
    assert {c.detail for c in descriptions.changes} == {"description changed"}
    assert demo.runs[5].ontology_version == 3
    assert demo.runs[5].conformance.score == 1.0


def test_v3_passes_every_gate_and_is_promoted_by_ci(demo):
    gates = demo.gates_v3
    assert gates.ontology_version == 3
    assert gates.passed
    assert [o.gate.name for o in gates.outcomes] == [
        "no-breaking-changes",
        "graph-conforms",
        "no-type-collapses",
        "properties-filled",
        "shallow-hierarchy",
        "no-duplicate-structures",
        "questions-answerable",
    ]
    answerability = result(demo.mara.get_evaluation_results(KG, 3), "structural_answerability")
    assert answerability.metrics["answerable_ratio"] == 0.875
    production = [p for p in demo.mara.list_promotions(KG) if p.alias == "production"]
    assert [(p.from_version, p.to_version, p.actor, p.gate_result) for p in production] == [
        (None, 1, "stetiq", None),
        (1, 3, "ci-bot", "passed"),
        (3, 4, "ci-bot", "passed"),
    ]


def test_the_label_scope_keeps_the_audit_nodes_out_of_every_observation(demo):
    observations = demo.mara.list_observations(KG)
    assert len(observations) == 16  # 6 build runs, 8 weekly Observations, 2 nightly runs
    for o in observations:
        assert o.scope.label == "Retail"
        assert "Audit" not in {t.label for t in o.schema.node_types}
        assert "Retail" not in {t.label for t in o.schema.node_types}
    first = demo.weeks[1].observation.schema
    assert {t.label for t in first.node_types} == {
        "Customer", "Order", "OrderLine", "Product", "Category", "Department",
        "Supplier", "Warehouse", "Shipment", "Return",
    }  # fmt: skip
    assert next(t.count for t in first.node_types if t.label == "Department") == 6
    assert next(t.count for t in first.node_types if t.label == "Category") == 46


def test_the_season_raises_exactly_three_drift_events(demo):
    assert {n for n, w in demo.weeks.items() if w.drifted} == {4, 5, 6}
    events = demo.mara.list_drift_events(KG)
    assert [e.observation_id for e in events] == [demo.weeks[n].observation.id for n in (4, 5, 6)]
    assert all(e.ontology_version == 3 and e.contract_alias == "production" for e in events)

    flash_sale = demo.weeks[4].drift
    assert flash_sale.structural == ()
    assert {(str(f.kind), f.subject) for f in flash_sale.statistical} == {
        ("count_increase", "Order"),
        ("count_increase", "OrderLine"),
        ("count_increase", "PLACED"),
        ("count_increase", "CONTAINS"),
        ("count_increase", "OF_PRODUCT"),
    }
    orders = next(f for f in flash_sale.statistical if f.subject == "Order")
    assert (orders.previous_count, orders.observed_count) == (3146, 8337)

    bins = {(str(f.kind), f.subject) for f in demo.weeks[5].drift.findings}
    assert bins == {
        ("undeclared", "Bin"),
        ("undeclared", "Bin.aisle"),
        ("undeclared", "Bin.code"),
        ("undeclared", "Bin.warehouse"),
        ("undeclared", "STORED_IN"),
    }

    retention = demo.weeks[6].drift
    assert {(str(f.kind), f.subject) for f in retention.structural} == bins
    assert {(str(f.kind), f.subject) for f in retention.statistical} == {
        ("count_drop", "Shipment"),
        ("count_drop", "FULFILLS"),
        ("count_drop", "SHIPPED_FROM"),
    }
    shipments = next(f for f in retention.statistical if f.subject == "Shipment")
    assert (shipments.previous_count, shipments.observed_count) == (5733, 3975)
    # Drift never creates an Ontology Version: v4 was registered by hand in week 7.
    assert [(v.number, v.origin) for v in demo.mara.list_ontology_versions(KG)] == [
        (1, "registered"),
        (2, "run"),
        (3, "registered"),
        (4, "registered"),
    ]


def test_strict_mode_fails_the_week_six_run_and_two_gates_with_it(demo):
    run = demo.week6_run
    assert run.status == "failed"
    assert run.candidate_version is None
    assert run.ontology_version == 3
    assert run.conformance.score == pytest.approx(66 / 72)
    gates = demo.gates_week6
    assert gates.subject_kind == "construction_run"
    assert {o.gate.name for o in gates.failed} == {"graph-conforms", "no-type-collapses"}
    [collapses] = [o for o in gates.outcomes if o.gate.name == "no-type-collapses"]
    assert any("Shipment: 3975 -> 2465" in reason for reason in collapses.reasons)


def test_v4_declares_the_bins_and_takes_over_production(demo):
    assert demo.mara.diff_ontology_versions(KG, 3, 4).classification == "additive"
    assert demo.week7_run.status == "finished"
    assert demo.week7_run.ontology_version == 4
    assert demo.week7_run.conformance.score == 1.0
    assert demo.gates_v4.passed
    assert demo.mara.get_contract_version(KG).number == 4
    assert demo.mara.get_evolution_mode(KG) == "strict"
    assert not demo.weeks[7].drifted and not demo.weeks[8].drifted
    last = demo.weeks[8].observation.schema
    assert (len(last.node_types), len(last.relationship_types), len(last.patterns)) == (11, 10, 11)
    assert sum(t.count for t in last.node_types) == 37678


def test_the_tracking_database_holds_structure_and_no_instance_data(demo):
    records = demo.season.records
    email = records[0].email.encode()
    assert email.endswith(b"@example.com")
    raw = demo.db_file.read_bytes()
    assert email not in raw
    assert records[0].name.encode() not in raw
    assert demo.seeds.products[0].name.encode() not in raw  # a product name
    assert b"TRK" not in raw  # no tracking number
    assert b"Customer" in raw and b"Shipment" in raw  # the structure is there
